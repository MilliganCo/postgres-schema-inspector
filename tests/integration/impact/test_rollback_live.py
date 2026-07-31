"""Live rollback / catalog-unchanged evidence (plan Task 12 S2_rollback)."""

from __future__ import annotations

import hashlib

import psycopg
import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.impact.models.enums import Outcome
from pginspect.impact.run import run_impact

from tests.integration.impact._fixture_admin import apply_setup_sql, drop_fixture_schemas
from tests.integration.impact.conftest import fixture_dir

pytestmark = pytest.mark.integration


def _catalog_checksum(admin_dsn: str, schema: str) -> str:
    sql = """
    SELECT c.relname, c.relkind, a.attname, a.atttypid, a.attnum, i.relname AS index_name
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_catalog.pg_attribute a
      ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    LEFT JOIN pg_catalog.pg_index x ON x.indrelid = c.oid
    LEFT JOIN pg_catalog.pg_class i ON i.oid = x.indexrelid
    WHERE n.nspname = %s
    ORDER BY c.relname, a.attnum, i.relname
    """
    with psycopg.connect(admin_dsn) as conn:
        rows = conn.execute(sql, (schema,)).fetchall()
    payload = repr(rows).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_s2_rollback_leaves_catalog_and_txn_clean(
    admin_dsn: str,
    subject_connection_config: ConnectionConfig,
    impact_session_safety: SessionSafetyConfig,
) -> None:
    path = fixture_dir("T1")
    apply_setup_sql(admin_dsn, path / "setup.sql")
    try:
        before = _catalog_checksum(admin_dsn, "impact_t1")
        result = run_impact(
            path / "migration.sql", subject_connection_config, impact_session_safety
        )
        assert result.outcome is Outcome.COMPLETED
        after = _catalog_checksum(admin_dsn, "impact_t1")
        assert before == after

        # Subject connection must not leave an open transaction behind.
        import os

        password = os.environ.get("PGPASSWORD", "pginspect_test_ci")
        conninfo = (
            f"host={subject_connection_config.host} "
            f"port={subject_connection_config.port} "
            f"dbname={subject_connection_config.dbname} "
            f"user={subject_connection_config.user} "
            f"password={password}"
        )
        with psycopg.connect(conninfo) as conn:
            assigned = conn.execute("SELECT pg_catalog.txid_current_if_assigned()").fetchone()
            assert assigned is not None
            assert assigned[0] is None
    finally:
        drop_fixture_schemas(admin_dsn, "S2_rollback")
