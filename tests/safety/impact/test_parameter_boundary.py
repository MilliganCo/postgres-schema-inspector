"""Prove migration-derived identifiers travel only as bound parameters."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.impact.queries import IMPACT_QUERY_REGISTRY
from pginspect.impact.run import run_impact

from tests.safety.impact._helpers import RecordingBag, install_executor_recorder

pytestmark = pytest.mark.safety

SCHEMA = "impact_param_canary_7f03"
COLUMN = "migration_identifier_7f03"
TABLE = "t"
FULL_STATEMENT = f"ALTER TABLE {SCHEMA}.{TABLE}\nADD COLUMN {COLUMN} text;"


def _apply_param_canary_setup(admin_dsn: str) -> None:
    sql = f"""
DROP SCHEMA IF EXISTS {SCHEMA} CASCADE;
CREATE SCHEMA {SCHEMA};
CREATE TABLE {SCHEMA}.{TABLE} (id int PRIMARY KEY);
GRANT USAGE ON SCHEMA {SCHEMA} TO pginspect_test;
GRANT SELECT ON ALL TABLES IN SCHEMA {SCHEMA} TO pginspect_test;
"""
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(sql)


def _drop_param_canary(admin_dsn: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


def _flatten_params(value: object) -> list[object]:
    if isinstance(value, (list, tuple)):
        out: list[object] = []
        for item in value:
            out.extend(_flatten_params(item))
        return out
    return [value]


def test_migration_identifiers_use_bound_parameters(
    pg_dsn: str,
    subject_connection_config: ConnectionConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RecordingBag()
    install_executor_recorder(monkeypatch, recorder)
    migration = tmp_path / "param_canary_migration.sql"
    migration.write_text(FULL_STATEMENT + "\n", encoding="utf-8")

    _apply_param_canary_setup(pg_dsn)
    try:
        result = run_impact(migration, subject_connection_config, SessionSafetyConfig())
        assert result.statements
        assert recorder.events

        receiving: list[tuple[str, tuple[object, ...]]] = []
        for event in recorder.events:
            assert event.sql_text is IMPACT_QUERY_REGISTRY[event.query_id].sql
            assert FULL_STATEMENT not in event.sql_text
            assert "ALTER TABLE" not in event.sql_text
            assert SCHEMA not in event.sql_text
            assert COLUMN not in event.sql_text

            flat = _flatten_params(event.bound_parameters)
            if SCHEMA in flat or COLUMN in flat:
                receiving.append((event.query_id, event.bound_parameters))

        assert receiving, (
            "expected migration-derived schema/column identifiers in bound_parameters; "
            f"saw {[e.query_id for e in recorder.events]}"
        )
        assert any(SCHEMA in _flatten_params(params) for _, params in receiving)
    finally:
        _drop_param_canary(pg_dsn)
