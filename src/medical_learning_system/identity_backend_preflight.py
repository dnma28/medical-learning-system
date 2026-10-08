"""Read-only backend connection probe; no identity apply or credential export."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from .identity_correction import canonical_json_sha256
from .postgres_identity_correction import read_identity_snapshot

PROJECT_REF = "ggwxpmwtvyptwbiuhhsl"
POOLER_HOST = "aws-0-ap-south-1.pooler.supabase.com"
LOGICAL_SOURCE_ID = "costanzo-physiology"


def connection_parameters(environment: Mapping[str, str]) -> dict:
    """Pin the existing backend target; never accept a caller-supplied DSN/host."""
    parsed = urlsplit(environment.get("MLS_SUPABASE_URL", ""))
    if (
        parsed.scheme != "https"
        or parsed.netloc != PROJECT_REF + ".supabase.co"
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("MLS_SUPABASE_URL must identify the expected project")
    password = environment.get("SUPABASE_DB_PASSWORD", "")
    if not password:
        raise ValueError("SUPABASE_DB_PASSWORD is missing")
    return {
        "host": POOLER_HOST,
        "port": 5432,
        "dbname": "postgres",
        "user": "postgres." + PROJECT_REF,
        "password": password,
        "sslmode": "require",
        "connect_timeout": 10,
        "autocommit": True,
        "prepare_threshold": None,
    }


def snapshot_summary(connection) -> dict:
    """Set session read-only, then reuse the complete consistent snapshot reader."""
    with connection.cursor() as cursor:
        cursor.execute("SET default_transaction_read_only = on")
        cursor.execute("SET statement_timeout = '30s'")
    snapshot = read_identity_snapshot(connection, LOGICAL_SOURCE_ID)
    guards = ("physical_sources", "staging_rows", "certificate_rows")
    return {
        "status": "READ_ONLY_BACKEND_CONNECTION_PASS",
        "project_ref": PROJECT_REF,
        "logical_source_id": LOGICAL_SOURCE_ID,
        "logical_row_sha256": canonical_json_sha256(snapshot["logical_row"]),
        "snapshot_sha256": canonical_json_sha256(snapshot),
        "guard_counts": {name: len(snapshot[name]) for name in guards},
        "guard_sha256": {name: canonical_json_sha256(snapshot[name]) for name in guards},
        "production_apply_performed": False,
    }


def main() -> int:
    import psycopg

    try:
        parameters = connection_parameters(os.environ)
        with psycopg.connect(**parameters) as connection:
            summary = snapshot_summary(connection)
    except (psycopg.Error, ValueError) as exc:
        # Connection exceptions can include sensitive connection details.
        print("Backend preflight stopped: " + type(exc).__name__)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
