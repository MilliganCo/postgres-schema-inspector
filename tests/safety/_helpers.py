"""Observer helpers for safety write-probes (not packaged)."""

from __future__ import annotations

from urllib.parse import urlparse

import psycopg

ADMIN_USER = "pginspect_admin"
ADMIN_PASSWORD = "pginspect_admin_ci"
SUBJECT_USER = "pginspect_test"
SUBJECT_PASSWORD = "pginspect_test_ci"
SENTINEL_PAYLOAD = "sentinel-unchanged"


def _admin_conninfo(pg_endpoint: dict[str, str | int]) -> str:
    return (
        f"host={pg_endpoint.get('host', '127.0.0.1')} "
        f"port={pg_endpoint.get('port', 5432)} "
        f"dbname={pg_endpoint.get('dbname', 'postgres')} "
        f"user={ADMIN_USER} password={ADMIN_PASSWORD}"
    )


def _subject_conninfo(pg_endpoint: dict[str, str | int]) -> str:
    return (
        f"host={pg_endpoint.get('host', '127.0.0.1')} "
        f"port={pg_endpoint.get('port', 5432)} "
        f"dbname={pg_endpoint.get('dbname', 'postgres')} "
        f"user={SUBJECT_USER} password={SUBJECT_PASSWORD}"
    )


def read_sentinel(pg_endpoint: dict[str, str | int]) -> str:
    with psycopg.connect(_admin_conninfo(pg_endpoint)) as conn:
        row = conn.execute(
            "SELECT payload FROM pginspect_probe.write_probe WHERE id = 1"
        ).fetchone()
        assert row is not None
        return str(row[0])


def count_adversarial_tables(pg_endpoint: dict[str, str | int]) -> int:
    with psycopg.connect(_admin_conninfo(pg_endpoint)) as conn:
        row = conn.execute(
            """
            SELECT count(*) FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'pginspect_probe' AND c.relname = 'adversarial_tmp'
            """
        ).fetchone()
        assert row is not None
        return int(row[0])


def assert_subject_has_write_grants(pg_endpoint: dict[str, str | int]) -> None:
    """F-08: without DiagnosticSession, subject can write (proves not 42501-only)."""
    with psycopg.connect(_subject_conninfo(pg_endpoint), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO pginspect_probe.write_probe (id, payload) "
            "VALUES (42, 'grant-check') ON CONFLICT (id) DO UPDATE "
            "SET payload = EXCLUDED.payload"
        )
        conn.execute("DELETE FROM pginspect_probe.write_probe WHERE id = 42")


def parse_dsn(dsn: str) -> dict[str, str | int]:
    if "://" in dsn:
        parsed = urlparse(dsn)
        out: dict[str, str | int] = {}
        if parsed.hostname:
            out["host"] = parsed.hostname
        if parsed.port:
            out["port"] = int(parsed.port)
        db = parsed.path.lstrip("/") if parsed.path else ""
        if db:
            out["dbname"] = db
        return out
    out = {}
    for part in dsn.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key in {"host", "dbname"}:
            out[key] = value
        elif key == "port":
            out[key] = int(value)
    return out
