"""Optional real-session tests against a disposable LOCAL PostgreSQL database.

Never point these at a remote server: host is fixed to loopback and database to
snapshot_test. The fixture schema is created only in this disposable database.
"""
import importlib
import os
import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from snapshot.storage import ConcurrentSnapshotUpdate, load_context, persist
from snapshot_worker import process

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
module = importlib.import_module("snapshot.snapshot")


@unittest.skipUnless(os.getenv("SNAPSHOT_TEST_POSTGRES_PORT"), "requires disposable local PostgreSQL")
class PostgresTests(unittest.TestCase):
    def connect(self):
        import pg8000.dbapi
        return pg8000.dbapi.connect(
            host="127.0.0.1", port=int(os.environ["SNAPSHOT_TEST_POSTGRES_PORT"]),
            database="snapshot_test", user="postgres", password="snapshot-local-test-only",
        )

    def setUp(self):
        self.sql = self.connect()
        self.addCleanup(self.sql.close)
        cursor = self.sql.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS organisations (id bigint PRIMARY KEY, enabled boolean)")
        cursor.execute("CREATE TABLE IF NOT EXISTS sites (id bigint PRIMARY KEY, name text, organisation_id bigint, max_capacity integer, enabled boolean, created_at timestamptz)")
        cursor.execute("CREATE TABLE IF NOT EXISTS devices (id bigint PRIMARY KEY, name text, site_id bigint, enabled boolean, analyzed_until timestamptz, created_at timestamptz)")
        cursor.execute("CREATE TABLE IF NOT EXISTS site_snapshots (site_id bigint PRIMARY KEY, ts timestamptz, state jsonb, payload jsonb, updated_at timestamptz)")
        cursor.execute("CREATE TABLE IF NOT EXISTS organisation_snapshots (organisation_id bigint PRIMARY KEY, ts timestamptz, state jsonb, payload jsonb, updated_at timestamptz)")
        cursor.execute("TRUNCATE organisations, sites, devices, site_snapshots, organisation_snapshots")
        cursor.execute("INSERT INTO organisations VALUES (1,true)")
        cursor.execute("INSERT INTO sites VALUES (2,'Site',1,100,true,%s)", (NOW - timedelta(hours=2),))
        cursor.execute("INSERT INTO devices VALUES (3,'Device',2,true,%s,%s)", (NOW - timedelta(hours=2),) * 2)
        cursor.execute("INSERT INTO site_snapshots VALUES (2,%s,'{}','{}',%s)", (NOW - timedelta(hours=1),) * 2)
        cursor.execute("INSERT INTO organisation_snapshots VALUES (1,%s,'{}','{}',%s)", (NOW - timedelta(hours=1),) * 2)
        self.sql.commit()
        cursor.close()

    @contextmanager
    def runtime(self, _settings):
        sql = self.connect()
        self.runtime_calls += 1
        try:
            yield sql, self.bq
        finally:
            sql.close()

    def execute_worker(self, now=NOW):
        self.runtime_calls = 0
        self.bq = Mock(side_effect=AssertionError("No event query expected"))
        return process(1, runtime_factory=self.runtime, now=lambda: now)

    def timestamps(self):
        cursor = self.sql.cursor()
        cursor.execute("SELECT ts FROM site_snapshots UNION ALL SELECT ts FROM organisation_snapshots")
        rows = [row[0] for row in cursor.fetchall()]
        self.sql.commit()
        cursor.close()
        return rows

    def test_real_execution_time_only_and_duplicate(self):
        self.assertEqual("completed", self.execute_worker().status)
        self.assertEqual([NOW, NOW], self.timestamps())
        self.assertEqual("fresh", self.execute_worker().status)
        # Source watermark does not move; TIME_ONLY still advances persisted ts.
        later = NOW + timedelta(minutes=30)
        classifications = []
        original_plan = module._site_plan
        def capture_plan(*args):
            result = original_plan(*args)
            classifications.append(result[0][2])
            return result
        with patch.object(module, "_site_plan", side_effect=capture_plan):
            self.assertEqual("completed", self.execute_worker(later).status)
        self.assertEqual(["TIME_ONLY"], classifications)
        self.assertEqual([later, later], self.timestamps())
        self.bq.assert_not_called()

    def test_real_skips_have_no_writes(self):
        for table, expected in [("organisation_snapshots", "organisation_snapshot_missing"),
                                ("site_snapshots", "site_snapshot_missing"),
                                ("sites", "no_sites"), ("organisations", "organisation_missing")]:
            with self.subTest(table=table):
                cursor = self.sql.cursor()
                cursor.execute(f"DELETE FROM {table}")  # fixed fixture identifiers only
                self.sql.commit()
                before = self.timestamps()
                with patch.object(module, "_run_attempt") as calculation:
                    self.assertEqual(expected, self.execute_worker().status)
                    calculation.assert_not_called()
                self.assertEqual(before, self.timestamps())
                self.bq.assert_not_called()
                self.setUp()

    def test_genuine_noop_direct_execution_does_not_write(self):
        self.assertEqual("completed", self.execute_worker().status)
        with patch.object(module, "persist", wraps=module.persist) as write:
            result = process(1, runtime_factory=self.runtime, now=lambda: NOW, cooldown=False)
        self.assertTrue(result.success)
        self.assertEqual("completed", result.status)
        write.assert_not_called()
        self.bq.assert_not_called()

    def test_same_session_exclusivity_survives_commit_and_rollback(self):
        other = self.connect()
        self.addCleanup(other.close)
        cursor = other.cursor()
        def calculation(sql, *_):
            sql.commit()
            cursor.execute("SELECT pg_try_advisory_lock(-1::bigint), pg_try_advisory_lock(-2::bigint)")
            self.assertEqual([False, True], list(cursor.fetchone()))
            sql.rollback()
            cursor.execute("SELECT pg_try_advisory_lock(-1::bigint)")
            self.assertFalse(cursor.fetchone()[0])
            return True
        with patch.object(module, "run_on_connection", side_effect=calculation):
            self.assertEqual("completed", self.execute_worker().status)
        cursor.execute("SELECT pg_try_advisory_lock(-1::bigint)")
        self.assertTrue(cursor.fetchone()[0])
        cursor.close()

    def test_lost_physical_session_cannot_commit_or_reconnect(self):
        other = self.connect()
        self.addCleanup(other.close)
        cursor = other.cursor()
        def lose_session(sql, *_):
            own = sql.cursor()
            own.execute("SELECT pg_backend_pid()")
            pid = own.fetchone()[0]
            sql.commit()
            cursor.execute("SELECT pg_terminate_backend(%s)", (pid,))
            self.assertTrue(cursor.fetchone()[0])
            other.commit()
            # The old connection cannot perform a write through a new session.
            own.execute("UPDATE organisation_snapshots SET ts=%s", (NOW,))
            sql.commit()
        before = self.timestamps()
        with patch.object(module, "run_on_connection", side_effect=lose_session):
            with self.assertRaises(Exception):
                self.execute_worker()
        self.assertEqual(1, self.runtime_calls)
        self.assertEqual(before, self.timestamps())
        cursor.execute("SELECT pg_try_advisory_lock(-1::bigint)")
        self.assertTrue(cursor.fetchone()[0])
        cursor.close()

    def test_atomic_site_update_rolled_back_on_org_conflict(self):
        context = load_context(self.sql, 1)
        self.sql.commit()
        context["organisation_snapshot"]["version"] = NOW - timedelta(days=1)
        before = self.timestamps()
        candidate = (NOW, {"changed": True}, {"changed": True})
        with self.assertRaises(ConcurrentSnapshotUpdate):
            persist(self.sql, context, {2: candidate}, candidate)
        self.assertEqual(before, self.timestamps())

    def test_failure_releases_lock(self):
        with patch.object(module, "run_on_connection", side_effect=ValueError("calculation failed")):
            with self.assertRaises(ValueError):
                self.execute_worker()
        cursor = self.sql.cursor()
        cursor.execute("SELECT pg_try_advisory_lock(-1::bigint)")
        self.assertTrue(cursor.fetchone()[0])
        cursor.execute("SELECT pg_advisory_unlock(-1::bigint)")
        self.sql.commit()
        cursor.close()
