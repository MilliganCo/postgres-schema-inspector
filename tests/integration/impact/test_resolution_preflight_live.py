"""Live design §2 resolution / preflight fixtures (plan Task 12)."""

from __future__ import annotations

import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.connection import open_connection
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ExecutionPrediction,
    NoOpReason,
    Outcome,
    PreflightStatus,
    Risk,
)
from pginspect.impact.run import run_impact
from pginspect.session import DiagnosticSession

from tests.integration.impact._fixture_admin import apply_setup_sql, drop_fixture_schemas
from tests.integration.impact.conftest import (
    fixture_dir,
    subject_env_scs_off,
    subject_env_search_path,
)

pytestmark = pytest.mark.integration


def test_s2_shadow_first_match_search_path(
    admin_dsn: str,
    subject_connection_config: ConnectionConfig,
    impact_session_safety: SessionSafetyConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.integration.conftest import SUBJECT_PASSWORD

    monkeypatch.setenv("PGPASSWORD", SUBJECT_PASSWORD)
    path = fixture_dir("S2_shadow")
    apply_setup_sql(admin_dsn, path / "setup.sql")
    try:
        with subject_env_search_path("impact_s2_a,impact_s2_b"):
            with open_connection(subject_connection_config) as conn:
                session = DiagnosticSession(conn, impact_session_safety)
                try:
                    profile = session.establish_impact_profile()
                    from pginspect.impact.resolve import resolve_relation

                    resolved = resolve_relation(
                        schema=None,
                        name="t",
                        context=profile.resolution_context,
                        executor=session.as_query_executor(),
                    )
                finally:
                    session.force_rollback()
            assert resolved.status == "resolved"
            assert resolved.nspname == "impact_s2_a"
            result = run_impact(
                path / "migration.sql",
                subject_connection_config,
                impact_session_safety,
            )
        assert result.outcome is Outcome.COMPLETED
        assert result.exit_code == 1
        card = result.statements[0]
        assert card.analysis_status is AnalysisStatus.ANALYZED
        assert "rule:add.nullable.no_default" in card.evidence_refs
    finally:
        drop_fixture_schemas(admin_dsn, "S2_shadow")


def test_s2_partition_unsupported_scope(
    admin_dsn: str,
    subject_connection_config: ConnectionConfig,
    impact_session_safety: SessionSafetyConfig,
) -> None:
    path = fixture_dir("S2_partition")
    apply_setup_sql(admin_dsn, path / "setup.sql")
    try:
        result = run_impact(
            path / "migration.sql", subject_connection_config, impact_session_safety
        )
        assert result.outcome is Outcome.INCOMPLETE
        assert result.exit_code == 3
        card = result.statements[0]
        assert card.analysis_status is AnalysisStatus.UNSUPPORTED_SCOPE
        assert card.execution_prediction is ExecutionPrediction.NOT_EVALUATED
        assert card.risk is Risk.NOT_APPLICABLE
    finally:
        drop_fixture_schemas(admin_dsn, "S2_partition")


def test_s2_inherit_unsupported_scope(
    admin_dsn: str,
    subject_connection_config: ConnectionConfig,
    impact_session_safety: SessionSafetyConfig,
) -> None:
    path = fixture_dir("S2_inherit")
    apply_setup_sql(admin_dsn, path / "setup.sql")
    try:
        result = run_impact(
            path / "migration.sql", subject_connection_config, impact_session_safety
        )
        assert result.outcome is Outcome.INCOMPLETE
        assert result.exit_code == 3
        card = result.statements[0]
        assert card.analysis_status is AnalysisStatus.UNSUPPORTED_SCOPE
        assert card.execution_prediction is ExecutionPrediction.NOT_EVALUATED
        assert card.risk is Risk.NOT_APPLICABLE
    finally:
        drop_fixture_schemas(admin_dsn, "S2_inherit")


def test_s2_missing_if_exists_safe_noop(
    admin_dsn: str,
    subject_connection_config: ConnectionConfig,
    impact_session_safety: SessionSafetyConfig,
) -> None:
    path = fixture_dir("S2_missing_if_exists")
    apply_setup_sql(admin_dsn, path / "setup.sql")
    try:
        result = run_impact(
            path / "migration.sql", subject_connection_config, impact_session_safety
        )
        assert result.outcome is Outcome.COMPLETED
        assert result.exit_code == 0
        card = result.statements[0]
        assert card.execution_prediction is ExecutionPrediction.NO_OP
        assert card.no_op_reason is NoOpReason.TARGET_MISSING_IF_EXISTS
        assert card.risk is Risk.SAFE
    finally:
        drop_fixture_schemas(admin_dsn, "S2_missing_if_exists")


def test_s2_scs_off_preflight_incomplete(
    admin_dsn: str,
    subject_connection_config: ConnectionConfig,
    impact_session_safety: SessionSafetyConfig,
) -> None:
    path = fixture_dir("S2_scs_off")
    apply_setup_sql(admin_dsn, path / "setup.sql")
    try:
        with subject_env_scs_off():
            result = run_impact(
                path / "migration.sql",
                subject_connection_config,
                impact_session_safety,
            )
        assert result.outcome is Outcome.INCOMPLETE
        assert result.exit_code == 3
        assert result.preflight.status is PreflightStatus.INCOMPLETE
        assert result.statements == ()
        scs_checks = [c for c in result.preflight.checks if "standard_conforming_strings" in c.id]
        assert scs_checks
        assert any("off" in c.detail.lower() for c in scs_checks)
    finally:
        drop_fixture_schemas(admin_dsn, "S2_scs_off")


def test_live_rr_ro_and_hardened_search_path(
    subject_connection_config: ConnectionConfig,
    impact_session_safety: SessionSafetyConfig,
) -> None:
    with open_connection(subject_connection_config) as conn:
        session = DiagnosticSession(conn, impact_session_safety)
        try:
            profile = session.establish_impact_profile()
            ctx = profile.connection_context
            assert ctx.transaction_isolation.lower().replace("-", " ") in {
                "repeatable read",
                "repeatable_read",
            }
            assert ctx.transaction_read_only in {"on", "true", "1"}
            assert profile.resolution_context.current_schemas_with_implicit
            assert "pg_catalog" in profile.resolution_context.current_schemas_with_implicit
        finally:
            session.force_rollback()
