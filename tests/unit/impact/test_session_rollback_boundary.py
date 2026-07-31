"""Session-owned rollback boundary for impact orchestration (Layer D Blocker C)."""

from __future__ import annotations

import ast
from pathlib import Path
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.exceptions import PginspectInternalError
from pginspect.impact.models.result import ImpactConnectionContext
from pginspect.impact.models.enums import Outcome
from pginspect.impact.parse_local import LocalParsedScript, LocalStatement
from pginspect.impact.preflight import PreflightEvaluation, ResolutionContext
from pginspect.impact.run import run_impact
from pginspect.session import DiagnosticSession, ImpactSessionState


SRC_IMPACT = Path(__file__).resolve().parents[3] / "src" / "pginspect" / "impact"


def _script() -> LocalParsedScript:
    return LocalParsedScript(
        path_basename="migration.sql",
        statements=(
            LocalStatement(
                statement_index=1,
                is_control=False,
                start_line=1,
                end_line=1,
                tokens=(),
                statement_fingerprint="sha256:0000000000000001",
                sanitized_preview="ALTER TABLE t DROP COLUMN c",
            ),
        ),
        control_ordinals=(),
        source_statement_count=1,
    )


def _profile() -> ImpactSessionState:
    return ImpactSessionState(
        resolution_context=ResolutionContext(
            database="db",
            role="r",
            session_user="r",
            current_schema="public",
            current_schemas_user=("public",),
            current_schemas_with_implicit=("pg_catalog", "public"),
            search_path_raw='"public"',
            max_identifier_length_bytes=63,
            server_major=16,
            server_version_num=160000,
            keyword_categories={},
        ),
        connection_context=ImpactConnectionContext(
            server_version="16.0",
            server_version_num=160000,
            server_major=16,
            database="db",
            role="r",
            session_user="r",
            current_schema="public",
            search_path_raw='"public"',
            standard_conforming_strings="on",
            server_encoding="UTF8",
            client_encoding="UTF8",
            transaction_isolation="repeatable read",
            transaction_read_only="on",
            in_recovery=False,
            max_identifier_length=63,
        ),
        catalog_snapshot_at=datetime(2026, 7, 31, tzinfo=UTC),
    )


def test_impact_source_never_calls_connection_rollback_or_cursor() -> None:
    forbidden_attrs = {"rollback", "cursor", "commit"}
    offenders: list[str] = []
    for path in sorted(SRC_IMPACT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
                offenders.append(f"{path.relative_to(SRC_IMPACT)}: .{node.attr}")
    assert offenders == [], f"impact/* must not own raw connection ops: {offenders}"


def test_run_impact_calls_session_force_rollback_not_connection_rollback() -> None:
    fake_conn = MagicMock()
    session = MagicMock()
    session.establish_impact_profile.return_value = _profile()
    session.as_query_executor.return_value = MagicMock()

    class _CM:
        def __enter__(self) -> MagicMock:
            return fake_conn

        def __exit__(self, *args: object) -> None:
            return None

    from pginspect.impact.analysis_unit import AnalysisUnit
    from pginspect.impact.models.enums import AnalysisStatus
    from pginspect.impact.parser.ast import SourceSpan
    from pginspect.impact.run import EarlyOutcomeKind, EarlySemanticOutcome

    unit = AnalysisUnit(
        statement_index=1,
        source_span=SourceSpan(1, 1, 0, 10),
        statement_fingerprint="sha256:0000000000000001",
        sanitized_preview="x",
        family="drop",
        ast=object(),
        analysis_status=AnalysisStatus.ANALYZED,
        table_oid=None,
        table_schema="public",
        table_name="t",
        column_attnum=None,
        column_normalized_name="c",
        resolution_payload=EarlySemanticOutcome(EarlyOutcomeKind.TARGET_MISSING_IF_EXISTS),
        evidence_ids=(),
        requires_virtual_schema_state=False,
        limitations=(),
    )

    with (
        patch("pginspect.impact.run.parse_migration_path", return_value=_script()),
        patch("pginspect.impact.run.open_connection", return_value=_CM()),
        patch("pginspect.impact.run.DiagnosticSession", return_value=session),
        patch(
            "pginspect.impact.run.evaluate_preflight_gates",
            return_value=PreflightEvaluation(False, ()),
        ),
        patch("pginspect.impact.run._build_unit_for_statement", return_value=unit),
        patch("pginspect.impact.run.apply_sequence_constraints", side_effect=lambda u: tuple(u)),
    ):
        result = run_impact(
            Path("migration.sql"),
            ConnectionConfig(host="localhost"),
            SessionSafetyConfig(),
        )

    assert result.outcome is Outcome.COMPLETED
    session.force_rollback.assert_called_once()
    fake_conn.rollback.assert_not_called()


def test_force_rollback_failure_maps_to_internal_failed_result() -> None:
    fake_conn = MagicMock()
    session = MagicMock()
    session.establish_impact_profile.return_value = _profile()
    session.as_query_executor.return_value = MagicMock()
    session.force_rollback.side_effect = PginspectInternalError("rollback boom")

    class _CM:
        def __enter__(self) -> MagicMock:
            return fake_conn

        def __exit__(self, *args: object) -> None:
            return None

    from pginspect.impact.analysis_unit import AnalysisUnit
    from pginspect.impact.models.enums import AnalysisStatus
    from pginspect.impact.parser.ast import SourceSpan
    from pginspect.impact.run import EarlyOutcomeKind, EarlySemanticOutcome

    unit = AnalysisUnit(
        statement_index=1,
        source_span=SourceSpan(1, 1, 0, 10),
        statement_fingerprint="sha256:0000000000000001",
        sanitized_preview="x",
        family="drop",
        ast=object(),
        analysis_status=AnalysisStatus.ANALYZED,
        table_oid=None,
        table_schema="public",
        table_name="t",
        column_attnum=None,
        column_normalized_name="c",
        resolution_payload=EarlySemanticOutcome(EarlyOutcomeKind.TARGET_MISSING_IF_EXISTS),
        evidence_ids=(),
        requires_virtual_schema_state=False,
        limitations=(),
    )

    with (
        patch("pginspect.impact.run.parse_migration_path", return_value=_script()),
        patch("pginspect.impact.run.open_connection", return_value=_CM()),
        patch("pginspect.impact.run.DiagnosticSession", return_value=session),
        patch(
            "pginspect.impact.run.evaluate_preflight_gates",
            return_value=PreflightEvaluation(False, ()),
        ),
        patch("pginspect.impact.run._build_unit_for_statement", return_value=unit),
        patch("pginspect.impact.run.apply_sequence_constraints", side_effect=lambda u: tuple(u)),
    ):
        result = run_impact(
            Path("migration.sql"),
            ConnectionConfig(host="localhost"),
            SessionSafetyConfig(),
        )

    assert result.outcome is Outcome.FAILED
    assert result.exit_code == 5
    assert result.error is not None


def test_diagnostic_session_force_rollback_uses_connection_seam() -> None:
    conn = MagicMock()
    session = DiagnosticSession(conn, SessionSafetyConfig())
    session.force_rollback()
    conn.rollback.assert_called_once()
