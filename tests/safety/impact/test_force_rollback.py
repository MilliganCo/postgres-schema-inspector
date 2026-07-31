"""force_rollback seam evidence (plan Task 13)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.impact.run import run_impact
from pginspect.session import DiagnosticSession

from tests.integration.impact._fixture_admin import apply_setup_sql, drop_fixture_schemas

pytestmark = pytest.mark.safety


def test_run_impact_calls_session_force_rollback(
    pg_dsn: str,
    subject_connection_config: ConnectionConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_setup_sql(pg_dsn, Path("tests/fixtures/impact/A1/setup.sql"))
    calls: list[str] = []
    real_force = DiagnosticSession.force_rollback

    def tracked(self: DiagnosticSession) -> None:
        calls.append("force_rollback")
        return real_force(self)

    monkeypatch.setattr(DiagnosticSession, "force_rollback", tracked)
    try:
        run_impact(
            Path("tests/fixtures/impact/A1/migration.sql"),
            subject_connection_config,
            SessionSafetyConfig(),
        )
        assert calls == ["force_rollback"]
    finally:
        drop_fixture_schemas(pg_dsn, "A1")


def test_impact_package_has_no_raw_connection_rollback() -> None:
    import ast
    from pathlib import Path

    root = Path("src/pginspect/impact")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"rollback", "cursor", "commit"}:
                offenders.append(f"{path}: .{node.attr}")
    assert offenders == []
