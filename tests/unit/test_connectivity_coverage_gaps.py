"""Coverage for session-phase error remapping and version finding branches."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest

from pginspect.capabilities import DiscoveredCapabilities
from pginspect.config import ConnectTestConfig, ConnectionConfig
from pginspect.connectivity import (
    build_connect_operational_failure,
    build_preconnect_internal_failure,
    run_connect_test,
)
from pginspect.exceptions import (
    ConnectFailedError,
    ConnectNetworkError,
    ConnectTlsError,
    PginspectInternalError,
)
from pginspect.models.context import ConnectionTargetContext, PrivilegeSnapshot
from pginspect.models.enums import (
    ClassificationSource,
    CommandExitCode,
    CommandOutcome,
    ConnectionTargetSource,
    ExecutionErrorCategory,
    ExecutionErrorCode,
    FindingId,
    VersionSupportStatus,
)
from pginspect.models.execution_error import ExecutionError
from pginspect.models.finding import (
    ConnectionFailedEvidence,
    ConnectionFailedFinding,
    ConnectionFindingScope,
    SessionSafetyVerifiedEvidence,
)
from pginspect.session import SessionState, TransportMetadata


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


@contextmanager
def _fake_open_connection(_config: ConnectionConfig) -> Iterator[MagicMock]:
    conn = MagicMock()
    conn.pgconn.ssl_in_use = True
    yield conn


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


def _scope() -> ConnectionFindingScope:
    return ConnectionFindingScope(
        target=ConnectionTargetContext(
            explicit_host_fingerprint=None,
            source=ConnectionTargetSource.LIBPQ_RESOLVED_UNKNOWN,
        )
    )


def test_builder_rejects_non_connection_operational_failure() -> None:
    finding = ConnectionFailedFinding(
        title="Could not connect to PostgreSQL",
        scope=_scope(),
        evidence=ConnectionFailedEvidence(
            category="connection_failed",
            classification_source=ClassificationSource.FALLBACK_OTHER,
            sqlstate=None,
        ),
    )
    error = ExecutionError(
        code=ExecutionErrorCode.INTERNAL_FAILURE,
        category=ExecutionErrorCategory.INTERNAL,
        message="pginspect failed due to an internal error.",
        retryable=False,
    )
    with pytest.raises(ValueError, match="error.category=connection"):
        build_connect_operational_failure(
            finding=finding,
            error=error,
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
        )


def test_builder_rejects_non_internal_preconnect_failure() -> None:
    error = ExecutionError(
        code=ExecutionErrorCode.CONNECTION_FAILED,
        category=ExecutionErrorCategory.CONNECTION,
        message="Could not connect to PostgreSQL.",
        retryable=True,
    )
    with pytest.raises(ValueError, match="error.category=internal"):
        build_preconnect_internal_failure(
            error=error,
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
        )


def test_session_network_error_before_verify_is_operational() -> None:
    err = ConnectNetworkError(
        code=ExecutionErrorCode.NETWORK_UNREACHABLE,
        classification_source=ClassificationSource.SQLSTATE,
        sqlstate="08006",
        driver_exception_type="ConnectionFailure",
        debug_frames=(),
    )
    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(enter_error=err),
        ),
    ):
        result = run_connect_test(ConnectTestConfig(), include_debug=True)

    assert result.outcome is CommandOutcome.FAILED
    assert result.exit_code is CommandExitCode.OPERATIONAL_FAILURE
    assert result.context is None
    assert [f.id for f in result.findings] == [FindingId.CONNECTION_ESTABLISHED]
    assert result.error is not None
    assert result.error.code is ExecutionErrorCode.OPERATIONAL_FAILURE
    assert result.error.category is ExecutionErrorCategory.OPERATIONAL
    assert result.error.debug is not None


def test_session_operational_failure_after_verify() -> None:
    err = ConnectFailedError(
        code=ExecutionErrorCode.OPERATIONAL_FAILURE,
        classification_source=ClassificationSource.SQLSTATE,
        sqlstate="57014",
    )
    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(),
        ),
        patch(
            "pginspect.connectivity.discover_capabilities",
            side_effect=err,
        ),
    ):
        result = run_connect_test(ConnectTestConfig(), include_debug=True)

    assert result.outcome is CommandOutcome.FAILED
    assert result.exit_code is CommandExitCode.OPERATIONAL_FAILURE
    assert [f.id for f in result.findings] == [
        FindingId.CONNECTION_ESTABLISHED,
        FindingId.CONNECTION_SESSION_SAFETY_VERIFIED,
    ]
    assert result.error is not None
    assert result.error.code is ExecutionErrorCode.OPERATIONAL_FAILURE
    assert result.error.category is ExecutionErrorCategory.OPERATIONAL


def test_session_tls_error_remapped_to_operational() -> None:
    err = ConnectTlsError(
        code=ExecutionErrorCode.TLS_FAILED,
        classification_source=ClassificationSource.AUDITED_TLS_SIGNAL,
    )
    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(),
        ),
        patch("pginspect.connectivity.discover_capabilities", side_effect=err),
    ):
        result = run_connect_test(ConnectTestConfig())

    assert result.error is not None
    assert result.error.code is ExecutionErrorCode.OPERATIONAL_FAILURE
    assert result.error.category is ExecutionErrorCategory.OPERATIONAL


def test_session_internal_before_verify() -> None:
    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(enter_error=PginspectInternalError("boom")),
        ),
    ):
        result = run_connect_test(ConnectTestConfig(), include_debug=True)

    assert result.outcome is CommandOutcome.FAILED
    assert result.exit_code is CommandExitCode.INTERNAL_FAILURE
    assert [f.id for f in result.findings] == [FindingId.CONNECTION_ESTABLISHED]
    assert result.error is not None
    assert result.error.debug is not None


def test_session_internal_after_verify() -> None:
    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(),
        ),
        patch(
            "pginspect.connectivity.discover_capabilities",
            side_effect=PginspectInternalError("discover boom"),
        ),
    ):
        result = run_connect_test(ConnectTestConfig())

    assert result.exit_code is CommandExitCode.INTERNAL_FAILURE
    assert [f.id for f in result.findings] == [
        FindingId.CONNECTION_ESTABLISHED,
        FindingId.CONNECTION_SESSION_SAFETY_VERIFIED,
    ]


def test_unexpected_exception_becomes_internal() -> None:
    @contextmanager
    def boom(_config: ConnectionConfig) -> Iterator[Any]:
        raise ValueError("totally unexpected")
        yield  # pragma: no cover

    with patch("pginspect.connectivity.open_connection", boom):
        result = run_connect_test(ConnectTestConfig())

    assert result.outcome is CommandOutcome.FAILED
    assert result.exit_code is CommandExitCode.INTERNAL_FAILURE
    assert result.findings == ()


def test_experimental_version_finding() -> None:
    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(),
        ),
        patch(
            "pginspect.connectivity.discover_capabilities",
            return_value=_discovered(
                version="19beta2",
                version_num=190000,
                major=19,
                major_label="19",
            ),
        ),
    ):
        result = run_connect_test(ConnectTestConfig())

    assert result.context is not None
    assert result.context.version_support is VersionSupportStatus.EXPERIMENTAL
    assert result.findings[-1].id is FindingId.CONNECTION_SERVER_VERSION_EXPERIMENTAL
    assert result.exit_code is CommandExitCode.WARNING


def test_untested_newer_version_finding() -> None:
    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(),
        ),
        patch(
            "pginspect.connectivity.discover_capabilities",
            return_value=_discovered(
                version="20.0",
                version_num=200000,
                major=20,
                major_label="20",
            ),
        ),
    ):
        result = run_connect_test(ConnectTestConfig())

    assert result.context is not None
    assert result.context.version_support is VersionSupportStatus.UNTESTED_NEWER
    assert result.findings[-1].id is FindingId.CONNECTION_SERVER_VERSION_UNTESTED


def test_unsupported_legacy_version_finding() -> None:
    with (
        patch("pginspect.connectivity.open_connection", _fake_open_connection),
        patch(
            "pginspect.connectivity.DiagnosticSession",
            return_value=_SessionCM(),
        ),
        patch(
            "pginspect.connectivity.discover_capabilities",
            return_value=_discovered(
                version="9.6.24",
                version_num=90624,
                major=None,
                major_label="9.6",
            ),
        ),
    ):
        result = run_connect_test(ConnectTestConfig())

    assert result.context is not None
    assert result.context.version_support is VersionSupportStatus.UNSUPPORTED_LEGACY
    evidence = result.findings[-1].evidence
    assert getattr(evidence, "version_support") == "unsupported_legacy"
