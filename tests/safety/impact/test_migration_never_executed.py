"""Migration SQL must never reach executable SQL text (plan Task 13)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.impact.run import run_impact

from tests.integration.impact._fixture_admin import apply_setup_sql, drop_fixture_schemas
from tests.safety.impact._helpers import (
    RecordingBag,
    assert_migration_absent_from_sql,
    canary_migration_path,
    install_executor_recorder,
)

pytestmark = pytest.mark.safety


def test_migration_statement_never_appears_in_executable_sql(
    pg_dsn: str,
    subject_connection_config: ConnectionConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RecordingBag()
    install_executor_recorder(monkeypatch, recorder)
    setup = Path("tests/fixtures/impact/T1/setup.sql")
    apply_setup_sql(pg_dsn, setup)
    try:
        path = canary_migration_path(tmp_path)
        # Use real T1 migration body plus canary marker already in helper text.
        path.write_text(
            (
                Path("tests/fixtures/impact/T1/migration.sql").read_text(encoding="utf-8")
                + "\n-- CANARY_MIGRATION_MUST_NEVER_EXECUTE\n"
            ),
            encoding="utf-8",
        )
        result = run_impact(path, subject_connection_config, SessionSafetyConfig())
        assert result.statements
        assert recorder.events
        assert_migration_absent_from_sql(recorder.events)
        for event in recorder.events:
            for param in event.bound_parameters:
                if isinstance(param, str):
                    assert "CANARY_MIGRATION_MUST_NEVER_EXECUTE" not in param
    finally:
        drop_fixture_schemas(pg_dsn, "T1")
