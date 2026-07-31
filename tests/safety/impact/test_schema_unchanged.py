"""Catalog unchanged after impact analysis (plan Task 13)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import psycopg
import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.impact.run import run_impact

from tests.integration.impact._fixture_admin import apply_setup_sql, drop_fixture_schemas

pytestmark = pytest.mark.safety


def _checksum(admin_dsn: str, schema: str) -> str:
    sql = """
    SELECT c.relname, c.relkind, a.attname, a.atttypid, a.attnum
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_catalog.pg_attribute a
      ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    WHERE n.nspname = %s
    ORDER BY c.relname, a.attnum
    """
    with psycopg.connect(admin_dsn) as conn:
        rows = conn.execute(sql, (schema,)).fetchall()
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


def test_schema_unchanged_after_impact(
    pg_dsn: str,
    subject_connection_config: ConnectionConfig,
) -> None:
    apply_setup_sql(pg_dsn, Path("tests/fixtures/impact/T1/setup.sql"))
    try:
        before = _checksum(pg_dsn, "impact_t1")
        run_impact(
            Path("tests/fixtures/impact/T1/migration.sql"),
            subject_connection_config,
            SessionSafetyConfig(),
        )
        after = _checksum(pg_dsn, "impact_t1")
        assert before == after
    finally:
        drop_fixture_schemas(pg_dsn, "T1")
