"""Demo fixture matrix for live impact analysis (plan Task 12)."""

from __future__ import annotations

import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.impact.models.enums import Outcome

from tests.integration.impact._fixture_admin import apply_setup_sql, drop_fixture_schemas
from tests.integration.impact.conftest import (
    DEMO_FIXTURE_IDS,
    assert_expected_projection,
    fixture_dir,
    load_expected,
    run_fixture,
    semantic_projection,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("fixture_id", DEMO_FIXTURE_IDS)
def test_demo_fixture_matrix(
    fixture_id: str,
    admin_dsn: str,
    subject_connection_config: ConnectionConfig,
    impact_session_safety: SessionSafetyConfig,
    server_major: int,
) -> None:
    result = run_fixture(
        fixture_id,
        admin_dsn=admin_dsn,
        connection_config=subject_connection_config,
        session_safety=impact_session_safety,
    )
    expected = load_expected(fixture_id, server_major)
    assert_expected_projection(result, expected)


def test_a4_a5_semantic_projection_equal(
    admin_dsn: str,
    subject_connection_config: ConnectionConfig,
    impact_session_safety: SessionSafetyConfig,
) -> None:
    a4 = run_fixture(
        "A4",
        admin_dsn=admin_dsn,
        connection_config=subject_connection_config,
        session_safety=impact_session_safety,
    )
    a5 = run_fixture(
        "A5",
        admin_dsn=admin_dsn,
        connection_config=subject_connection_config,
        session_safety=impact_session_safety,
    )
    assert semantic_projection(a4) == semantic_projection(a5)


def test_d2_d3_use_live_pg_class_classoid(
    admin_dsn: str,
    subject_connection_config: ConnectionConfig,
    impact_session_safety: SessionSafetyConfig,
) -> None:
    from pginspect.connection import open_connection
    from pginspect.impact.catalog import fetch_pg_class_classoid
    from pginspect.session import DiagnosticSession

    with open_connection(subject_connection_config) as conn:
        session = DiagnosticSession(conn, impact_session_safety)
        try:
            session.establish_impact_profile()
            classoid = fetch_pg_class_classoid(session.as_query_executor())
        finally:
            session.force_rollback()
    assert classoid is not None and classoid > 0

    for fixture_id in ("D2", "D3"):
        result = run_fixture(
            fixture_id,
            admin_dsn=admin_dsn,
            connection_config=subject_connection_config,
            session_safety=impact_session_safety,
        )
        assert result.outcome is Outcome.COMPLETED
        assert result.exit_code == 2
        assert any(ref.startswith("dep:view:") for ref in result.statements[0].evidence_refs)


def test_setup_sql_is_idempotent(admin_dsn: str) -> None:
    setup = fixture_dir("T1") / "setup.sql"
    apply_setup_sql(admin_dsn, setup)
    apply_setup_sql(admin_dsn, setup)
    drop_fixture_schemas(admin_dsn, "T1")
    drop_fixture_schemas(admin_dsn, "T1")
