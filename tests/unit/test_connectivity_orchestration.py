"""Mocked orchestration tests for run_connect_test stages."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest
from pydantic import TypeAdapter

from pginspect.capabilities import DiscoveredCapabilities
from pginspect.config import ConnectTestConfig, ConnectionConfig
from pginspect.connectivity import run_connect_test
from pginspect.exceptions import (
    ConnectAuthenticationError,
    PginspectInternalError,
    SessionSafetyError,
)
from pginspect.models.context import PrivilegeSnapshot
from pginspect.models.enums import (
    ClassificationSource,
    CommandExitCode,
    CommandOutcome,
    ExecutionErrorCode,
    FindingId,
    SessionSafetyMisconfigurationCategory,
    VersionSupportStatus,
)
from pginspect.models.finding import SessionSafetyExpectedState, SessionSafetyVerifiedEvidence
from pginspect.models.result import CommandResult, ConnectTestCommandResult
from pginspect.session import SessionState, TransportMetadata


def _scope_target_host() -> ConnectionConfig:
    return ConnectionConfig(host="secret-db.internal.example", connect_timeout_s=10)


@contextmanager
def _fake_open_connection(_config: ConnectionConfig) -> Iterator[MagicMock]:
    conn = MagicMock()
    conn.pgconn.ssl_in_use = True
    yield conn


def _verified_evidence() -> SessionSafetyVerifiedEvidence:
    return SessionSafetyVerifiedEvidence(
        default_transaction_read_only=True,
        transaction_read_only=True,
        statement_timeout_ms=15000,
        lock_timeout_ms=2000,
        idle_in_transaction_session_timeout_ms=15000,
        search_path=("pg_catalog",),
        application_name_kind="pginspect_owned",
        application_name_value="pginspect/0.1.0",
        write_probe="not_run",
        verification_level="settings",
        read_only_scope="postgresql_transaction",
        read_only_is_sandbox=False,
    )


def _discovered(
    *,
    version: str = "18.4",
    version_num: int = 180004,
    major: int | None = 18,
    major_label: str = "18",
) -> DiscoveredCapabilities:
    return DiscoveredCapabilities(
        database_name="shop",
        current_role="monitor",
        session_user="monitor",
        server_version=version,
        server_version_num=version_num,
        server_major=major,
        server_major_label=major_label,
        in_recovery=False,
        privileges=PrivilegeSnapshot(
            is_superuser=False,
            can_use_pg_monitor=True,
            can_use_pg_read_all_stats=True,
            can_use_pg_read_all_settings=False,
        ),
        installed_extensions=frozenset(),
    )


class _SessionCM:
    def __init__(
        self,
        *,
        enter_error: BaseException | None = None,
        evidence: SessionSafetyVerifiedEvidence | None = None,
    ) -> None:
        self._enter_error = enter_error
        self._evidence = evidence or _verified_evidence()
        self.state = SessionState.NEW

    def __enter__(self) -> _SessionCM:
        if self._enter_error is not None:
            self.state = SessionState.FAILED
            raise self._enter_error
        self.state = SessionState.READY
        return self

    def __exit__(self, *args: object) -> None:
        self.state = SessionState.CLOSED
        return None

    def transport_metadata(self) -> TransportMetadata:
        return TransportMetadata(tls_used=True)

    @property
    def verification_evidence(self) -> SessionSafetyVerifiedEvidence:
        return self._evidence


def test_auth_fail_only_connection_failed_exit_3() -> None:
    auth_err = ConnectAuthenticationError(
        code=ExecutionErrorCode.AUTHENTICATION_FAILED,
        classification_source=ClassificationSource.SQLSTATE,
        sqlstate="28P01",
    )

    @contextmanager
    def boom(_config: ConnectionConfig) -> Iterator[Any]:
        raise auth_err
        yield  # pragma: no cover

    with patch("pginspect.connectivity.open_connection", boom):
        result = run_connect_test(ConnectTestConfig())

    assert result.outcome is CommandOutcome.FAILED
    assert result.exit_code is CommandExitCode.OPERATIONAL_FAILURE
    assert result.context is None
    assert len(result.findings) == 1
    assert result.findings[0].id is FindingId.CONNECTION_FAILED
    assert result.error is not None
    assert result.error.code is ExecutionErrorCode.AUTHENTICATION_FAILED


def test_safety_misconfigured_exit_2_no_context() -> None:
    safety_err = SessionSafetyError(
        category=SessionSafetyMisconfigurationCategory.SET_REJECTED,
        expected=SessionSafetyExpectedState(
            default_transaction_read_only=True,
            transaction_read_only=True,
            statement_timeout_ms=15000,
            lock_timeout_ms=2000,
            idle_in_transaction_session_timeout_ms=15000,
            search_path=("pg_catalog",),
        ),
        observed=None,
        sqlstate="42501",
    )

    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(enter_error=safety_err),
        ),
    ):
        result = run_connect_test(ConnectTestConfig())

    assert result.outcome is CommandOutcome.COMPLETED
    assert result.exit_code is CommandExitCode.CRITICAL
    assert result.context is None
    assert result.error is None
    assert [f.id for f in result.findings] == [
        FindingId.CONNECTION_ESTABLISHED,
        FindingId.CONNECTION_SESSION_SAFETY_MISCONFIGURED,
    ]


def test_full_success_three_findings_context_exit_0() -> None:
    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(),
        ),
        patch(
            "pginspect.connectivity.discover_capabilities",
            return_value=_discovered(),
        ),
    ):
        result = run_connect_test(ConnectTestConfig())

    assert result.outcome is CommandOutcome.COMPLETED
    assert result.exit_code is CommandExitCode.OK
    assert result.context is not None
    assert result.context.version_support is VersionSupportStatus.SUPPORTED
    assert [f.id for f in result.findings] == [
        FindingId.CONNECTION_ESTABLISHED,
        FindingId.CONNECTION_SESSION_SAFETY_VERIFIED,
        FindingId.CONNECTION_SERVER_VERSION_SUPPORTED,
    ]


def test_unsupported_version_exit_2_completed() -> None:
    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(),
        ),
        patch(
            "pginspect.connectivity.discover_capabilities",
            return_value=_discovered(
                version="13.8",
                version_num=130008,
                major=13,
                major_label="13",
            ),
        ),
    ):
        result = run_connect_test(ConnectTestConfig())

    assert result.outcome is CommandOutcome.COMPLETED
    assert result.exit_code is CommandExitCode.CRITICAL
    assert result.context is not None
    assert result.context.version_support is VersionSupportStatus.UNSUPPORTED_OLDER
    assert result.findings[-1].id is FindingId.CONNECTION_SERVER_VERSION_UNSUPPORTED


def test_keyboard_interrupt_propagates() -> None:
    @contextmanager
    def interrupted(_config: ConnectionConfig) -> Iterator[Any]:
        raise KeyboardInterrupt
        yield  # pragma: no cover

    with patch("pginspect.connectivity.open_connection", interrupted):
        with pytest.raises(KeyboardInterrupt):
            run_connect_test(ConnectTestConfig())


def test_canary_absent_from_command_result_json_serialization() -> None:
    """Canary leakage check via CommandResult JSON only (no renderers)."""
    canary_password = "CANARY_PASSWORD_7f03"
    canary_host = "secret-db.internal.example"
    canary_dsn = "postgresql://monitor:CANARY_PASSWORD_7f03@secret-db.internal.example:5432/shop"
    canary_passfile = "/home/canary/.pgpass"
    canary_cert = "/etc/ssl/canary-client.crt"

    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(),
        ),
        patch(
            "pginspect.connectivity.discover_capabilities",
            return_value=_discovered(),
        ),
    ):
        result = run_connect_test(
            ConnectTestConfig(connection=_scope_target_host()),
            include_debug=True,
        )

    assert isinstance(result, ConnectTestCommandResult)
    assert result.context is not None
    assert result.context.target.explicit_host_fingerprint is not None
    assert canary_host not in result.context.target.explicit_host_fingerprint

    payload = TypeAdapter(CommandResult).dump_python(result, mode="json")
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    for canary in (canary_password, canary_host, canary_dsn, canary_passfile, canary_cert):
        assert canary not in text


def test_preconnect_internal_exit_5() -> None:
    @contextmanager
    def boom(_config: ConnectionConfig) -> Iterator[Any]:
        raise PginspectInternalError("preconnect boom")
        yield  # pragma: no cover

    with patch("pginspect.connectivity.open_connection", boom):
        result = run_connect_test(ConnectTestConfig())

    assert result.outcome is CommandOutcome.FAILED
    assert result.exit_code is CommandExitCode.INTERNAL_FAILURE
    assert result.findings == ()
    assert result.error is not None
    assert result.error.code is ExecutionErrorCode.INTERNAL_FAILURE
