"""Request-owned admission and execution. Never reconnect an admitted SQL session."""
import logging
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from config import Settings
from snapshot.storage import MissingPrerequisite, check_prerequisites, runtime

log = logging.getLogger(__name__)
MAX_ORGANISATION_ID = 2**63 - 1


def validate_id(value):
    if type(value) is not int or not 1 <= value <= MAX_ORGANISATION_ID:
        raise ValueError("organisation_id must be a positive signed-64-bit integer")
    return value


class InvalidSnapshotTimestamp(ValueError):
    pass


def is_fresh(value, now, minutes):
    # pg8000 returns timestamptz as aware datetime. Do not guess timezone/type.
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidSnapshotTimestamp("Snapshot timestamp must be an aware datetime")
    value = value.astimezone(timezone.utc)
    if value > now:
        raise InvalidSnapshotTimestamp("Snapshot timestamp is in the future")
    return now - value < timedelta(minutes=minutes)


@dataclass(frozen=True)
class Outcome:
    status: str
    success: bool


def process(organisation_id, *, settings=None, runtime_factory=None,
            now=None, cooldown=True):
    validate_id(organisation_id)
    settings = settings or Settings.from_env()
    runtime_factory = runtime_factory or runtime
    now = now or (lambda: datetime.now(timezone.utc))
    # A dedicated direct connection owns the lock and every subsequent write.
    # Closing this connection is the final release even if unlock/rollback fails.
    with runtime_factory(settings) as (sql, bq_factory):
        acquired = False
        try:
            with closing(sql.cursor()) as cursor:
                # Negative bigint keys are reserved for Snapshot in this database.
                cursor.execute("SELECT pg_try_advisory_lock(%s::bigint)", (-organisation_id,))
                acquired = cursor.fetchone()[0]
            sql.commit()  # session lock survives; avoid idle-in-transaction work
            if not acquired:
                return Outcome("busy", False)
            try:
                timestamp = check_prerequisites(sql, organisation_id)
            except MissingPrerequisite as exc:
                log.info("snapshot_skipped organisation_id=%s reason=%s", organisation_id, exc.reason)
                return Outcome(exc.reason, False)
            admitted_at = now()
            fresh = is_fresh(timestamp, admitted_at, settings.refresh_minutes)
            sql.commit()
            if cooldown and fresh:
                return Outcome("fresh", True)
            from snapshot.snapshot import run_on_connection
            result = run_on_connection(sql, organisation_id, bq_factory,
                                       admitted_at.replace(microsecond=0))
            return Outcome("completed" if result else "missing_prerequisite", result)
        finally:
            # Cleanup must not mask an execution error or imply a failed commit.
            # runtime always closes the physical session, including on SQL loss.
            try:
                sql.rollback()
                if acquired:
                    with closing(sql.cursor()) as cursor:
                        cursor.execute("SELECT pg_advisory_unlock(%s::bigint)", (-organisation_id,))
                        if not cursor.fetchone()[0]:
                            log.error("snapshot_lock_missing organisation_id=%s", organisation_id)
                    sql.commit()
            except Exception:
                log.warning("snapshot_session_cleanup_failed organisation_id=%s", organisation_id)
