"""Allowlisted QuerySpec execution evidence (plan Task 13)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.impact.queries import IMPACT_QUERY_REGISTRY
from pginspect.impact.run import run_impact

from tests.integration.impact._fixture_admin import apply_setup_sql, drop_fixture_schemas
from tests.safety.impact._helpers import (
    RecordingBag,
    assert_allowlisted,
    install_executor_recorder,
)

pytestmark = pytest.mark.safety


def test_every_executed_query_id_is_registry_allowlisted(
    pg_dsn: str,
    subject_connection_config: ConnectionConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RecordingBag()
    install_executor_recorder(monkeypatch, recorder)
    apply_setup_sql(pg_dsn, Path("tests/fixtures/impact/A1/setup.sql"))
    try:
        run_impact(
            Path("tests/fixtures/impact/A1/migration.sql"),
            subject_connection_config,
            SessionSafetyConfig(),
        )
        assert recorder.events
        assert_allowlisted(recorder.events)
        for event in recorder.events:
            assert event.sql_text == IMPACT_QUERY_REGISTRY[event.query_id].sql
    finally:
        drop_fixture_schemas(pg_dsn, "A1")


def test_registry_mutation_cannot_change_production_mapping() -> None:
    original = IMPACT_QUERY_REGISTRY["impact.fetch_relation"].sql
    with pytest.raises(TypeError):
        IMPACT_QUERY_REGISTRY["impact.fetch_relation"] = None  # type: ignore[index]
    with pytest.raises(Exception):
        IMPACT_QUERY_REGISTRY["impact.fetch_relation"].sql = "SELECT 1"  # type: ignore[misc]
    assert IMPACT_QUERY_REGISTRY["impact.fetch_relation"].sql == original
    assert IMPACT_QUERY_REGISTRY["impact.fetch_relation"].sql is original
