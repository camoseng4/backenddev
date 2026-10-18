"""Cloud SQL context and atomic optimistic Snapshot persistence."""

import json
from contextlib import contextmanager
from contextlib import closing

from config import Settings

from .site_engine import stamp


INSTANCE = "camosbase:europe-west2:camos-prod-postgres"
DATABASE = "camos_prod"


class ConcurrentSnapshotUpdate(RuntimeError):
    pass


class MissingPrerequisite(Exception):
    """An intentional skip, never a database/credential/calculation failure."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def check_prerequisites(connection, organisation_id):
    """Read-only preflight before interpreting state or doing any calculation."""
    with closing(connection.cursor()) as cursor:
        cursor.execute("SELECT id FROM public.organisations WHERE id=%s", (organisation_id,))
        if cursor.fetchone() is None:
            raise MissingPrerequisite("organisation_missing")
        cursor.execute("SELECT id FROM public.sites WHERE organisation_id=%s ORDER BY id", (organisation_id,))
        site_ids = [int(row[0]) for row in cursor.fetchall()]
        if not site_ids:
            raise MissingPrerequisite("no_sites")
        cursor.execute("SELECT ts FROM public.organisation_snapshots WHERE organisation_id=%s", (organisation_id,))
        row = cursor.fetchone()
        if row is None:
            raise MissingPrerequisite("organisation_snapshot_missing")
        timestamp = row[0]
        cursor.execute("SELECT site_id FROM public.site_snapshots WHERE site_id = ANY(%s)", (site_ids,))
        if set(site_ids) - {int(row[0]) for row in cursor.fetchall()}:
            raise MissingPrerequisite("site_snapshot_missing")
        return timestamp


def credentials():
    import google.auth
    return google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])[0]


@contextmanager
def runtime(settings):
    """One physical SQL session per execution. No pool, reconnect or JSON key."""
    from google.cloud.sql.connector import Connector
    from google.cloud import bigquery
    snapshot_credentials = credentials()
    client = None
    connector = Connector(credentials=snapshot_credentials, refresh_strategy="lazy")
    try:
        with connection(connector, snapshot_credentials, settings) as sql:
            def bq_factory():
                nonlocal client
                if client is None:
                    client = bigquery.Client(credentials=snapshot_credentials,
                                             project=settings.project,
                                             location=settings.bigquery_location)
                return client
            yield sql, bq_factory
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            connector.close()


@contextmanager
def connection(connector, snapshot_credentials, settings=None):
    from google.cloud.sql.connector import IPTypes
    settings = settings or Settings.from_env()
    # ADC metadata email may be unresolved before refresh. Use explicit identity;
    # Connector authenticates the actual ADC principal, so a mismatch fails closed.
    email = settings.service_account
    value = connector.connect(
        settings.instance, "pg8000",
        user=email.removesuffix(".gserviceaccount.com"), db=settings.database,
        enable_iam_auth=True, ip_type=getattr(IPTypes, settings.ip_type),
        timeout=30,
    )
    try:
        yield value
    finally:
        value.close()


def _json(value):
    if isinstance(value, str):
        value = json.loads(value)
    return value


def load_context(connection, organisation_id):
    check_prerequisites(connection, organisation_id)
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT id,enabled FROM public.organisations WHERE id=%s",
            (organisation_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise MissingPrerequisite("organisation_missing")
        organisation = {
            "id": int(row[0]),
            "enabled": bool(row[1]),
        }

        cursor.execute(
            "SELECT id,name,organisation_id,max_capacity,enabled,created_at "
            "FROM public.sites WHERE organisation_id=%s ORDER BY id",
            (organisation_id,),
        )
        sites = [
            {
                "id": int(row[0]),
                "name": row[1],
                "organisation_id": int(row[2]),
                "max_capacity": int(row[3]),
                "enabled": bool(row[4]),
                "created_at": stamp(row[5]),
            }
            for row in cursor.fetchall()
        ]
        if not sites:
            raise MissingPrerequisite("no_sites")
        site_ids = [site["id"] for site in sites]
        devices_by_site = {site_id: [] for site_id in site_ids}
        if site_ids:
            cursor.execute(
                "SELECT id,name,site_id,enabled,analyzed_until,created_at "
                "FROM public.devices WHERE site_id = ANY(%s) ORDER BY site_id,id",
                (site_ids,),
            )
            for row in cursor.fetchall():
                devices_by_site[int(row[2])].append(
                    {
                        "id": int(row[0]),
                        "name": row[1],
                        "site_id": int(row[2]),
                        "enabled": bool(row[3]),
                        "analyzed_until": (
                            None if row[4] is None else stamp(row[4])
                        ),
                        "created_at": stamp(row[5]),
                    }
                )
            cursor.execute(
                "SELECT site_id,ts,state,updated_at FROM public.site_snapshots "
                "WHERE site_id = ANY(%s)",
                (site_ids,),
            )
            site_rows = {
                int(row[0]): {
                    "site_id": int(row[0]),
                    "ts": stamp(row[1]),
                    "state": _json(row[2]),
                    "version": row[3],
                }
                for row in cursor.fetchall()
            }
        else:
            site_rows = {}
        missing = sorted(set(site_ids) - set(site_rows))
        if missing:
            raise MissingPrerequisite("site_snapshot_missing")

        cursor.execute(
            "SELECT organisation_id,ts,state,updated_at "
            "FROM public.organisation_snapshots WHERE organisation_id=%s",
            (organisation_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise MissingPrerequisite("organisation_snapshot_missing")
        org_row = {
            "organisation_id": int(row[0]),
            "ts": stamp(row[1]),
            "state": _json(row[2]),
            "version": row[3],
        }
        context = {
            "organisation": organisation,
            "sites": sites,
            "devices_by_site": devices_by_site,
            "site_snapshots": site_rows,
            "organisation_snapshot": org_row,
        }
        context["fingerprint"] = membership_fingerprint(context)
        return context
    finally:
        cursor.close()


def membership_fingerprint(context):
    return (
        (context["organisation"]["id"], context["organisation"]["enabled"]),
        tuple(
            (
                site["id"],
                site["name"],
                site["organisation_id"],
                site["enabled"],
                site["created_at"],
                site["max_capacity"],
            )
            for site in context["sites"]
        ),
        tuple(
            (
                site_id,
                device["id"],
                device["name"],
                device["enabled"],
                device["created_at"],
            )
            for site_id in sorted(context["devices_by_site"])
            for device in context["devices_by_site"][site_id]
        ),
    )


def load_fingerprint(connection, organisation_id):
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT id,enabled FROM public.organisations WHERE id=%s",
            (organisation_id,),
        )
        organisation = cursor.fetchone()
        if organisation is None:
            raise ConcurrentSnapshotUpdate(
                "Organisation membership/configuration changed"
            )
        cursor.execute(
            "SELECT id,name,organisation_id,enabled,created_at,max_capacity "
            "FROM public.sites WHERE organisation_id=%s ORDER BY id",
            (organisation_id,),
        )
        sites = [
            {
                "id": int(row[0]),
                "name": row[1],
                "organisation_id": int(row[2]),
                "enabled": bool(row[3]),
                "created_at": stamp(row[4]),
                "max_capacity": int(row[5]),
            }
            for row in cursor.fetchall()
        ]
        site_ids = [site["id"] for site in sites]
        devices_by_site = {site_id: [] for site_id in site_ids}
        if site_ids:
            cursor.execute(
                "SELECT id,name,site_id,enabled,created_at FROM public.devices "
                "WHERE site_id = ANY(%s) ORDER BY site_id,id",
                (site_ids,),
            )
            for row in cursor.fetchall():
                devices_by_site[int(row[2])].append(
                    {
                        "id": int(row[0]),
                        "name": row[1],
                        "enabled": bool(row[3]),
                        "created_at": stamp(row[4]),
                    }
                )
        return membership_fingerprint(
            {
                "organisation": {
                    "id": int(organisation[0]),
                    "enabled": bool(organisation[1]),
                },
                "sites": sites,
                "devices_by_site": devices_by_site,
            }
        )
    finally:
        cursor.close()


def persist(connection, context, site_candidates, org_candidate):
    fresh = load_fingerprint(connection, context["organisation"]["id"])
    if fresh != context["fingerprint"]:
        raise ConcurrentSnapshotUpdate("Organisation membership/configuration changed")
    cursor = connection.cursor()
    try:
        for site_id, candidate in sorted(site_candidates.items()):
            cursor.execute(
                "UPDATE public.site_snapshots "
                "SET ts=%s,payload=%s::jsonb,state=%s::jsonb,updated_at=CURRENT_TIMESTAMP "
                "WHERE site_id=%s AND updated_at=%s RETURNING updated_at",
                (
                    candidate[0],
                    json.dumps(candidate[1]),
                    json.dumps(candidate[2]),
                    site_id,
                    context["site_snapshots"][site_id]["version"],
                ),
            )
            if cursor.fetchone() is None:
                raise ConcurrentSnapshotUpdate(f"Concurrent site snapshot update: {site_id}")
        if org_candidate is not None:
            cursor.execute(
                "UPDATE public.organisation_snapshots "
                "SET ts=%s,payload=%s::jsonb,state=%s::jsonb,updated_at=CURRENT_TIMESTAMP "
                "WHERE organisation_id=%s AND updated_at=%s RETURNING updated_at",
                (
                    org_candidate[0],
                    json.dumps(org_candidate[1]),
                    json.dumps(org_candidate[2]),
                    context["organisation"]["id"],
                    context["organisation_snapshot"]["version"],
                ),
            )
            if cursor.fetchone() is None:
                raise ConcurrentSnapshotUpdate("Concurrent organisation snapshot update")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
