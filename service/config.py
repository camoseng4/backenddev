"""Validated deployment settings; no credentials or network calls at import."""
import os
from dataclasses import dataclass


def positive_integer(name, default):
    value = os.getenv(name, str(default))
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


@dataclass(frozen=True)
class Settings:
    refresh_minutes: int = 30
    project: str = "camosbase"
    instance: str = "camosbase:europe-west2:camos-prod-postgres"
    database: str = "camos_prod"
    service_account: str = "processor@camosbase.iam.gserviceaccount.com"
    ip_type: str = "PUBLIC"
    bigquery_location: str | None = None

    @classmethod
    def from_env(cls):
        identity = os.getenv("PROCESSOR_SERVICE_ACCOUNT", cls.service_account)
        if not identity.endswith(".iam.gserviceaccount.com") or "@" not in identity:
            raise ValueError("PROCESSOR_SERVICE_ACCOUNT must be a service account email")
        ip_type = os.getenv("CLOUD_SQL_IP_TYPE", "PUBLIC").upper()
        if ip_type not in ("PUBLIC", "PRIVATE"):
            raise ValueError("CLOUD_SQL_IP_TYPE must be PUBLIC or PRIVATE")
        return cls(
            refresh_minutes=positive_integer("SNAPSHOT_REFRESH_INTERVAL_MINUTES", 30),
            project=os.getenv("GOOGLE_CLOUD_PROJECT", cls.project),
            instance=os.getenv("CLOUD_SQL_INSTANCE", cls.instance),
            database=os.getenv("CLOUD_SQL_DATABASE", cls.database),
            service_account=identity, ip_type=ip_type,
            bigquery_location=os.getenv("BIGQUERY_LOCATION") or None,
        )
