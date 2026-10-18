import importlib
import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from config import Settings
from snapshot.storage import MissingPrerequisite, check_prerequisites
from snapshot_worker import InvalidSnapshotTimestamp, Outcome, is_fresh, process

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
orchestration = importlib.import_module("snapshot.snapshot")


class Cursor:
    def __init__(self, sql):
        self.sql = sql
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def close(self):
        pass
    def execute(self, statement, parameters):
        self.sql.calls.append((statement, parameters))
        if "pg_try_advisory_lock" in statement:
            self.rows = [(self.sql.acquire,)]
        elif "pg_advisory_unlock" in statement:
            self.rows = [(True,)]
        else:
            self.rows = self.sql.results.pop(0)
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def fetchall(self):
        return self.rows


class SQL:
    def __init__(self, results=(), acquire=True):
        self.results = list(results)
        self.acquire = acquire
        self.calls = []
        self.commit = Mock()
        self.rollback = Mock()
        self.closed = False
    def cursor(self):
        return Cursor(self)


def factory(sql, bq):
    @contextmanager
    def runtime(_settings):
        try:
            yield sql, bq
        finally:
            sql.closed = True
    return runtime


def valid_rows(timestamp=NOW - timedelta(hours=1)):
    return [[(1,)], [(2,)], [(timestamp,)], [(2,)]]


class WorkerTests(unittest.TestCase):
    def test_missing_prerequisites_do_no_calculation_query_or_write(self):
        cases = [
            ([[]], "organisation_missing"),
            ([[(1,)], []], "no_sites"),
            ([[(1,)], [(2,)], []], "organisation_snapshot_missing"),
            ([[(1,)], [(2,)], [(NOW,)], []], "site_snapshot_missing"),
        ]
        for rows, expected in cases:
            with self.subTest(expected=expected):
                sql, bq = SQL(rows), Mock()
                with patch.object(orchestration, "_run_attempt") as calculation:
                    result = process(1, runtime_factory=factory(sql, bq), now=lambda: NOW)
                self.assertEqual(Outcome(expected, False), result)
                calculation.assert_not_called()
                bq.assert_not_called()
                self.assertFalse(any("UPDATE" in statement for statement, _ in sql.calls))
                self.assertTrue(sql.closed)
                self.assertTrue(any("pg_advisory_unlock" in statement for statement, _ in sql.calls))

    def test_public_snapshot_false_for_all_missing_cases(self):
        # Exercise public facade + real admission queries, not a mocked False.
        for rows in ([[]], [[(1,)], []], [[(1,)], [(2,)], []],
                     [[(1,)], [(2,)], [(NOW,)], []]):
            sql, bq = SQL(rows), Mock()
            with patch("snapshot_worker.runtime", factory(sql, bq)):
                self.assertIs(False, orchestration.Snapshot(1))
            bq.assert_not_called()

    def test_cooldown_boundary_and_duplicate_delivery(self):
        for age, expected in [(timedelta(minutes=29, seconds=59), "fresh"),
                              (timedelta(minutes=30), "completed"),
                              (timedelta(minutes=31), "completed")]:
            sql = SQL(valid_rows(NOW - age))
            with patch.object(orchestration, "run_on_connection", return_value=True) as run:
                result = process(1, runtime_factory=factory(sql, Mock()), now=lambda: NOW)
            self.assertEqual(expected, result.status)
            self.assertEqual(expected == "completed", run.called)
            if run.called:
                self.assertIs(sql, run.call_args.args[0])
        # Redelivery after durable timestamp advancement is a fresh skip.
        sql = SQL(valid_rows(NOW))
        with patch.object(orchestration, "run_on_connection") as run:
            self.assertEqual("fresh", process(1, runtime_factory=factory(sql, Mock()), now=lambda: NOW).status)
            run.assert_not_called()

    def test_bad_timestamps_raise_without_computation(self):
        for value in (None, "invalid", NOW.replace(tzinfo=None), NOW + timedelta(seconds=1)):
            sql = SQL(valid_rows(value))
            with patch.object(orchestration, "run_on_connection") as run:
                with self.assertRaises(InvalidSnapshotTimestamp):
                    process(1, runtime_factory=factory(sql, Mock()), now=lambda: NOW)
                run.assert_not_called()
            self.assertTrue(sql.closed)

    def test_busy_is_nonblocking_and_keys_are_distinct(self):
        keys = []
        for org in (1, 2, 2**63 - 1):
            sql = SQL(acquire=False)
            self.assertEqual("busy", process(org, runtime_factory=factory(sql, Mock())).status)
            keys.append(sql.calls[0][1][0])
            self.assertEqual(1, len(sql.calls))
        self.assertEqual([-1, -2, -(2**63 - 1)], keys)

    def test_query_error_propagates(self):
        sql = SQL(valid_rows())
        with patch("snapshot_worker.check_prerequisites", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                process(1, runtime_factory=factory(sql, Mock()))
        self.assertTrue(sql.closed)

    def test_execution_failure_unlocks_and_never_reconnects(self):
        sql, bq = SQL(valid_rows()), Mock()
        runtime = Mock(wraps=factory(sql, bq))
        with patch.object(orchestration, "run_on_connection", side_effect=ConnectionError("lost")):
            with self.assertRaises(ConnectionError):
                process(1, runtime_factory=runtime, now=lambda: NOW)
        runtime.assert_called_once()
        self.assertTrue(sql.closed)
        self.assertTrue(any("pg_advisory_unlock" in statement for statement, _ in sql.calls))

    def test_cleanup_error_does_not_mask_failure(self):
        sql = SQL(valid_rows())
        sql.rollback.side_effect = ConnectionError("dead session")
        with patch.object(orchestration, "run_on_connection", side_effect=RuntimeError("original")):
            with self.assertRaisesRegex(RuntimeError, "original"):
                process(1, runtime_factory=factory(sql, Mock()), now=lambda: NOW)
        self.assertTrue(sql.closed)

    def test_internal_errors_and_conflicts_raise(self):
        from snapshot.storage import ConcurrentSnapshotUpdate
        sql = SQL()
        for error, count in [(PermissionError("denied"), 1), (ConnectionError("lost"), 1),
                             (ValueError("bad state"), 1), (ConcurrentSnapshotUpdate(), 3)]:
            with patch.object(orchestration, "_run_attempt", side_effect=error) as attempt:
                with self.assertRaises(Exception):
                    orchestration.run_on_connection(sql, 1, Mock(), NOW)
                self.assertEqual(count, attempt.call_count)

    def test_success_and_noop_return_true(self):
        sql = SQL(valid_rows())
        with patch.object(orchestration, "_run_attempt", return_value=True):
            result = process(1, runtime_factory=factory(sql, Mock()), now=lambda: NOW)
        self.assertEqual(Outcome("completed", True), result)

    def test_real_all_noop_orchestration_returns_true_without_write(self):
        sql, bq = SQL(), Mock()
        context = {"sites": [{"id": 2}], "organisation_snapshot": {"ts": "2026-10-18T12:00:00Z"}}
        with patch.object(orchestration, "load_context", return_value=context), \
             patch.object(orchestration, "_site_plan", return_value=({2: "NO_OP"}, {}, {})), \
             patch.object(orchestration, "_org_classification", return_value=("NO_OP", {})), \
             patch.object(orchestration, "persist") as write, \
             patch.object(orchestration.site_engine, "compute_site") as calculate:
            self.assertIs(True, orchestration.run_on_connection(sql, 1, bq, NOW))
        write.assert_not_called()
        calculate.assert_not_called()
        bq.assert_not_called()

    def test_public_success_and_genuine_errors(self):
        for error in (None, PermissionError("denied"), ValueError("malformed state")):
            sql = SQL(valid_rows())
            with patch("snapshot_worker.runtime", factory(sql, Mock())), \
                 patch.object(orchestration, "_run_attempt", return_value=True, side_effect=error):
                if error is None:
                    self.assertIs(True, orchestration.Snapshot(1))
                else:
                    with self.assertRaises(type(error)):
                        orchestration.Snapshot(1)

    def test_adc_connection_identity_and_lazy_bigquery_cleanup(self):
        from snapshot import storage
        sql = Mock()
        connector = Mock()
        connector.connect.return_value = sql
        credential = Mock()
        with patch.object(storage, "credentials", return_value=credential), \
             patch("google.cloud.sql.connector.Connector", return_value=connector) as constructor, \
             patch("google.cloud.bigquery.Client") as bigquery:
            with storage.runtime(Settings()) as (physical, factory):
                self.assertIs(sql, physical)
                bigquery.assert_not_called()
                self.assertIs(bigquery.return_value, factory())
                self.assertIs(bigquery.return_value, factory())
            constructor.assert_called_once_with(credentials=credential, refresh_strategy="lazy")
            self.assertEqual("processor@camosbase.iam", connector.connect.call_args.kwargs["user"])
            self.assertIs(True, connector.connect.call_args.kwargs["enable_iam_auth"])
            bigquery.assert_called_once()
            bigquery.return_value.close.assert_called_once()
            sql.close.assert_called_once()
            connector.close.assert_called_once()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.processor = Mock(return_value=Outcome("completed", True))
        self.client = create_app(processor=self.processor, settings=Settings()).test_client()

    def test_health_is_process_only(self):
        self.assertEqual({"status": "ok"}, self.client.get("/health").json)
        self.processor.assert_not_called()

    def test_invalid_requests(self):
        for body in ({}, [], None, {"organisation_id": True}, {"organisation_id": 0},
                     {"organisation_id": -1}, {"organisation_id": 1.0},
                     {"organisation_id": "1"}, {"organisation_id": 2**63},
                     {"organisation_id": 1, "table": "unsafe"}):
            self.assertEqual(400, self.client.post("/tasks/snapshot", json=body).status_code)
        self.assertEqual(400, self.client.post("/tasks/snapshot", data="{").status_code)
        self.assertEqual(413, self.client.post("/tasks/snapshot", data="x" * 1025).status_code)
        self.processor.assert_not_called()

    def test_outcomes(self):
        for status in ("completed", "fresh", "no_sites", "organisation_missing",
                       "organisation_snapshot_missing", "site_snapshot_missing", "busy"):
            self.processor.return_value = Outcome(status, status in ("completed", "fresh"))
            response = self.client.post("/tasks/snapshot", json={"organisation_id": 1})
            self.assertEqual(503 if status == "busy" else 200, response.status_code)
            self.assertEqual(status, response.json["status"])

    def test_failure_is_retryable_without_detail_leak(self):
        self.processor.side_effect = RuntimeError("secret-internal-detail")
        response = self.client.post("/tasks/snapshot", json={"organisation_id": 1})
        self.assertEqual(503, response.status_code)
        self.assertEqual({"status": "failed"}, response.json)

    def test_settings(self):
        for value in ("0", "-1", "nan", "1.5", ""):
            with patch.dict("os.environ", SNAPSHOT_REFRESH_INTERVAL_MINUTES=value):
                with self.assertRaises(ValueError):
                    Settings.from_env()
        with patch.dict("os.environ", SNAPSHOT_REFRESH_INTERVAL_MINUTES="45"):
            self.assertEqual(45, Settings.from_env().refresh_minutes)


if __name__ == "__main__":
    unittest.main()
