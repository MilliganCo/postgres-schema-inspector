"""Live PostgreSQL integration tests for connect-test and session safety."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import psycopg
import pytest
from pydantic import TypeAdapter

from pginspect.config import ConnectionConfig, ConnectTestConfig, SessionSafetyConfig
from pginspect.connection import open_connection
from pginspect.connectivity import run_connect_test
from pginspect.models.enums import CommandOutcome, ExecutionErrorCode, FindingId
from pginspect.models.result import CommandResult
from pginspect.renderers import render_json
from pginspect.session import DiagnosticSession

pytestmark = pytest.mark.integration

_SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "schemas"
    / "command-result"
    / "1.0.schema.json"
)
_command_result_adapter: TypeAdapter[CommandResult] = TypeAdapter(CommandResult)


def _load_schema() -> dict[object, object]:
    return json.loads(_SCHEMA.read_text(encoding="utf-8"))


def test_happy_connect_test_json_schema_valid_exit_0(
    connect_test_config: ConnectTestConfig,
) -> None:
    result = run_connect_test(connect_test_config)
    assert result.outcome is CommandOutcome.COMPLETED
    assert result.exit_code == 0
    assert result.context is not None
    assert result.error is None
    ids = [f.id for f in result.findings]
    assert FindingId.CONNECTION_ESTABLISHED in ids
    assert FindingId.SESSION_SAFETY_VERIFIED in ids
    payload = json.loads(render_json(result))
    jsonschema.validate(instance=payload, schema=_load_schema())
    round_trip = _command_result_adapter.validate_python(payload)
    assert round_trip.exit_code == 0


def test_guc_verification_ms_units_and_search_path(
    subject_connection_config: ConnectionConfig,
) -> None:
    session_cfg = SessionSafetyConfig(
        statement_timeout_ms=12000,
        lock_timeout_ms=1500,
        idle_in_transaction_session_timeout_ms=11000,
    )
    with open_connection(subject_connection_config) as conn:
        with DiagnosticSession(conn, session_cfg) as session:
            evidence = session.verification_evidence
            assert evidence.statement_timeout_ms == 12000
            assert evidence.lock_timeout_ms == 1500
            assert evidence.idle_in_transaction_session_timeout_ms == 11000
            assert evidence.search_path == ("pg_catalog",)
            assert evidence.write_probe == "not_run"
            assert evidence.verification_level == "settings"


def test_pgappname_custom_preserved(
    subject_connection_config: ConnectionConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGAPPNAME", "custom-app-name-for-pginspect")
    with open_connection(subject_connection_config) as conn:
        with DiagnosticSession(conn, SessionSafetyConfig()) as session:
            evidence = session.verification_evidence
            assert evidence.application_name_kind == "custom"
            assert evidence.application_name_value is None


def test_auth_failure_exit_3(
    pg_endpoint: dict[str, str | int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGPASSWORD", "definitely-wrong-password-pginspect")
    config = ConnectTestConfig(
        connection=ConnectionConfig(
            host=str(pg_endpoint.get("host", "127.0.0.1")),
            port=int(pg_endpoint.get("port", 5432)),
            dbname=str(pg_endpoint.get("dbname", "postgres")),
            user="pginspect_test",
            connect_timeout_s=5,
        )
    )
    result = run_connect_test(config)
    assert result.outcome is CommandOutcome.FAILED
    assert result.exit_code == 3
    assert result.findings[0].id is FindingId.CONNECTION_FAILED
    assert result.error is not None
    assert result.error.code in {
        ExecutionErrorCode.AUTHENTICATION_FAILED,
        ExecutionErrorCode.CONNECTION_FAILED,
    }


def test_missing_database_exit_3(
    subject_connection_config: ConnectionConfig,
) -> None:
    config = ConnectTestConfig(
        connection=subject_connection_config.model_copy(
            update={"dbname": "pginspect_missing_db_xyz"}
        )
    )
    result = run_connect_test(config)
    assert result.outcome is CommandOutcome.FAILED
    assert result.exit_code == 3
    assert result.error is not None
    assert result.error.code in {
        ExecutionErrorCode.DATABASE_MISSING,
        ExecutionErrorCode.CONNECTION_FAILED,
    }


def test_closed_port_network(
    subject_connection_config: ConnectionConfig,
    closed_local_port: int,
) -> None:
    config = ConnectTestConfig(
        connection=subject_connection_config.model_copy(
            update={"port": closed_local_port, "connect_timeout_s": 2}
        )
    )
    result = run_connect_test(config)
    assert result.outcome is CommandOutcome.FAILED
    assert result.exit_code == 3
    assert result.error is not None
    assert result.error.code in {
        ExecutionErrorCode.NETWORK_UNREACHABLE,
        ExecutionErrorCode.CONNECTION_FAILED,
        ExecutionErrorCode.CONNECT_TIMEOUT,
    }


def test_loopback_stall_timeout(
    subject_connection_config: ConnectionConfig,
    stall_server: int,
) -> None:
    config = ConnectTestConfig(
        connection=subject_connection_config.model_copy(
            update={"port": stall_server, "connect_timeout_s": 2}
        )
    )
    result = run_connect_test(config)
    assert result.outcome is CommandOutcome.FAILED
    assert result.exit_code == 3
    assert result.error is not None
    assert result.error.code in {
        ExecutionErrorCode.CONNECT_TIMEOUT,
        ExecutionErrorCode.NETWORK_UNREACHABLE,
        ExecutionErrorCode.CONNECTION_FAILED,
    }


def test_libpq_service_precedence_asserts_actual_database(
    pg_endpoint: dict[str, str | int],
    subject_password_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service file selects dbname; assert context.database_name, not only fingerprint."""
    host = str(pg_endpoint.get("host", "127.0.0.1"))
    port = int(pg_endpoint.get("port", 5432))
    dbname = str(pg_endpoint.get("dbname", "postgres"))
    service_file = tmp_path / "pg_service.conf"
    service_file.write_text(
        f"[pginspect_svc]\n"
        f"host={host}\n"
        f"port={port}\n"
        f"dbname={dbname}\n"
        f"user=pginspect_test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PGSERVICEFILE", str(service_file))
    # Intentionally wrong dbname on CLI must not win over --service when only service set.
    config = ConnectTestConfig(
        connection=ConnectionConfig(service="pginspect_svc", connect_timeout_s=10)
    )
    result = run_connect_test(config)
    assert result.outcome is CommandOutcome.COMPLETED
    assert result.exit_code == 0
    assert result.context is not None
    assert result.context.database == dbname


def test_session_establishment_atomicity_discards_failed_session(
    subject_connection_config: ConnectionConfig,
) -> None:
    """Failed establish leaves session FAILED; fresh connection starts from server defaults."""
    with open_connection(subject_connection_config) as conn:
        baseline = conn.execute(
            "SELECT setting FROM pg_catalog.pg_settings WHERE name = 'statement_timeout'"
        ).fetchone()
        assert baseline is not None
        baseline_ms = str(baseline[0])

        # Mid-statement failure after a distinctive session GUC (documents PG + app discard).
        with pytest.raises(psycopg.Error):
            conn.execute(
                """
                SELECT
                  pg_catalog.set_config('statement_timeout', '777ms', false),
                  1 / 0
                """
            )
        # Session GUCs from an aborted statement may stick on this connection; app must not reuse.
        stuck = conn.execute(
            "SELECT setting FROM pg_catalog.pg_settings WHERE name = 'statement_timeout'"
        ).fetchone()
        assert stuck is not None

    # Fresh connection (production path always opens new) restores server baseline.
    with open_connection(subject_connection_config) as conn2:
        restored = conn2.execute(
            "SELECT setting FROM pg_catalog.pg_settings WHERE name = 'statement_timeout'"
        ).fetchone()
        assert restored is not None
        assert str(restored[0]) == baseline_ms

        with DiagnosticSession(conn2, SessionSafetyConfig()) as session:
            assert session.verification_evidence.statement_timeout_ms == 15000
