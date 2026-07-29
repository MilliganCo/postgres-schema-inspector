"""Validator error-path coverage for ConnectTestCommandResult."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from pginspect.models.context import (
    ConnectionContext,
    ConnectionTargetContext,
    KnownExtensionSnapshot,
    PrivilegeSnapshot,
)
from pginspect.models.enums import (
    ClassificationSource,
    CommandExitCode,
    CommandOutcome,
    ConnectionTargetSource,
    ExecutionErrorCategory,
    ExecutionErrorCode,
    ExtensionAvailability,
    VersionSupportStatus,
)
from pginspect.models.execution_error import ExecutionError
from pginspect.models.finding import (
    ConnectionEstablishedEvidence,
    ConnectionEstablishedFinding,
    ConnectionFailedEvidence,
    ConnectionFailedFinding,
    ConnectionFindingScope,
    ServerVersionSupportedEvidence,
    ServerVersionSupportedFinding,
    SessionSafetyVerifiedEvidence,
    SessionSafetyVerifiedFinding,
)
from pginspect.models.result import ConnectTestCommandResult, VersionCommandResult


def _scope() -> ConnectionFindingScope:
    return ConnectionFindingScope(
        target=ConnectionTargetContext(
            explicit_host_fingerprint=None,
            source=ConnectionTargetSource.LIBPQ_RESOLVED_UNKNOWN,
        )
    )


def _established() -> ConnectionEstablishedFinding:
    return ConnectionEstablishedFinding(
        title="PostgreSQL connection established",
        scope=_scope(),
        evidence=ConnectionEstablishedEvidence(tls_used=True),
    )


def _verified() -> SessionSafetyVerifiedFinding:
    return SessionSafetyVerifiedFinding(
        title="Diagnostic session safety settings are active",
        scope=_scope(),
        evidence=SessionSafetyVerifiedEvidence(
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
        ),
    )


def _version() -> ServerVersionSupportedFinding:
    return ServerVersionSupportedFinding(
        title="PostgreSQL server version is supported",
        scope=_scope(),
        evidence=ServerVersionSupportedEvidence(
            server_version="18.4",
            server_version_num=180004,
            server_major=18,
            server_major_label="18",
            version_support="supported",
            supported_majors=(14, 15, 16, 17, 18),
            max_tested_stable_major=18,
            tested_prerelease_majors=(19,),
        ),
    )


def _context() -> ConnectionContext:
    return ConnectionContext(
        database="shop",
        role="monitor",
        session_user="monitor",
        server_version="18.4",
        server_version_num=180004,
        server_major=18,
        server_major_label="18",
        version_support=VersionSupportStatus.SUPPORTED,
        in_recovery=False,
        target=ConnectionTargetContext(
            explicit_host_fingerprint=None,
            source=ConnectionTargetSource.LIBPQ_RESOLVED_UNKNOWN,
        ),
        privileges=PrivilegeSnapshot(
            is_superuser=False,
            can_use_pg_monitor=True,
            can_use_pg_read_all_stats=True,
            can_use_pg_read_all_settings=False,
        ),
        extensions=KnownExtensionSnapshot(
            hypopg=ExtensionAvailability.UNAVAILABLE,
            pg_stat_statements=ExtensionAvailability.UNAVAILABLE,
            pgstattuple=ExtensionAvailability.UNAVAILABLE,
            pg_buffercache=ExtensionAvailability.UNAVAILABLE,
        ),
    )


def _conn_error() -> ExecutionError:
    return ExecutionError(
        code=ExecutionErrorCode.AUTHENTICATION_FAILED,
        category=ExecutionErrorCategory.CONNECTION,
        message="PostgreSQL authentication failed.",
        retryable=False,
        sqlstate="28P01",
        classification_source=ClassificationSource.SQLSTATE,
    )


def _failed_finding() -> ConnectionFailedFinding:
    return ConnectionFailedFinding(
        title="Could not connect to PostgreSQL",
        scope=_scope(),
        evidence=ConnectionFailedEvidence(
            category="authentication_failed",
            classification_source=ClassificationSource.SQLSTATE,
            sqlstate="28P01",
        ),
    )


def test_completed_rejects_non_null_error() -> None:
    with pytest.raises(ValidationError, match="error=null"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.COMPLETED,
            exit_code=CommandExitCode.OK,
            context=None,
            findings=(_established(),),
            error=_conn_error(),
        )


def test_completed_rejects_exit_3() -> None:
    with pytest.raises(ValidationError, match="exit_code in \\{0,1,2\\}"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.COMPLETED,
            exit_code=CommandExitCode.OPERATIONAL_FAILURE,
            context=None,
            findings=(_established(),),
            error=None,
        )


def test_failed_requires_error() -> None:
    with pytest.raises(ValidationError, match="failed outcome requires error"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.FAILED,
            exit_code=CommandExitCode.OPERATIONAL_FAILURE,
            context=None,
            findings=(_failed_finding(),),
            error=None,
        )


def test_failed_rejects_exit_0() -> None:
    with pytest.raises(ValidationError, match="exit_code in \\{3,5\\}"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.FAILED,
            exit_code=CommandExitCode.OK,
            context=None,
            findings=(_failed_finding(),),
            error=_conn_error(),
        )


def test_failed_exit_must_match_error_category() -> None:
    with pytest.raises(ValidationError, match="does not match error category"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.FAILED,
            exit_code=CommandExitCode.OPERATIONAL_FAILURE,
            context=None,
            findings=(),
            error=ExecutionError(
                code=ExecutionErrorCode.INTERNAL_FAILURE,
                category=ExecutionErrorCategory.INTERNAL,
                message="pginspect failed due to an internal error.",
                retryable=False,
            ),
        )


def test_connection_failed_must_be_only_finding() -> None:
    with pytest.raises(ValidationError, match="only finding"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.FAILED,
            exit_code=CommandExitCode.OPERATIONAL_FAILURE,
            context=None,
            findings=(_failed_finding(), _established()),
            error=_conn_error(),
        )


def test_connection_failed_requires_null_context() -> None:
    with pytest.raises(ValidationError, match="context=null"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.FAILED,
            exit_code=CommandExitCode.OPERATIONAL_FAILURE,
            context=_context(),
            findings=(_failed_finding(),),
            error=_conn_error(),
        )


def test_connection_failed_requires_failed_outcome() -> None:
    with pytest.raises(ValidationError, match="outcome=failed"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.COMPLETED,
            exit_code=CommandExitCode.CRITICAL,
            context=None,
            findings=(_failed_finding(),),
            error=None,
        )


def test_connection_failed_requires_exit_3() -> None:
    with pytest.raises(ValidationError, match="exit_code=3"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.FAILED,
            exit_code=CommandExitCode.INTERNAL_FAILURE,
            context=None,
            findings=(_failed_finding(),),
            error=ExecutionError(
                code=ExecutionErrorCode.INTERNAL_FAILURE,
                category=ExecutionErrorCategory.INTERNAL,
                message="pginspect failed due to an internal error.",
                retryable=False,
            ),
        )


def test_connection_failed_requires_connection_category() -> None:
    with pytest.raises(ValidationError, match="error.category=connection"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.FAILED,
            exit_code=CommandExitCode.OPERATIONAL_FAILURE,
            context=None,
            findings=(_failed_finding(),),
            error=ExecutionError(
                code=ExecutionErrorCode.AUTHENTICATION_FAILED,
                category=ExecutionErrorCategory.OPERATIONAL,
                message="PostgreSQL authentication failed.",
                retryable=False,
            ),
        )


def test_connection_failed_evidence_must_match_error_code() -> None:
    with pytest.raises(ValidationError, match="evidence.category must match"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.FAILED,
            exit_code=CommandExitCode.OPERATIONAL_FAILURE,
            context=None,
            findings=(_failed_finding(),),
            error=ExecutionError(
                code=ExecutionErrorCode.NETWORK_UNREACHABLE,
                category=ExecutionErrorCategory.CONNECTION,
                message="Could not reach PostgreSQL.",
                retryable=True,
            ),
        )


def test_version_finding_requires_context() -> None:
    with pytest.raises(ValidationError, match="version finding requires non-null context"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.COMPLETED,
            exit_code=CommandExitCode.OK,
            context=None,
            findings=(_established(), _verified(), _version()),
            error=None,
        )


def test_context_requires_safety_verified() -> None:
    with pytest.raises(ValidationError, match="session_safety_verified"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.COMPLETED,
            exit_code=CommandExitCode.OK,
            context=_context(),
            findings=(_established(), _version()),
            error=None,
        )


def test_context_requires_exactly_one_version_finding() -> None:
    with pytest.raises(ValidationError, match="exactly one version finding"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.COMPLETED,
            exit_code=CommandExitCode.OK,
            context=_context(),
            findings=(_established(), _verified()),
            error=None,
        )


def test_version_support_must_match_context() -> None:
    mismatched_ctx = _context().model_copy(
        update={"version_support": VersionSupportStatus.EXPERIMENTAL}
    )
    with pytest.raises(ValidationError, match="version_support"):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.COMPLETED,
            exit_code=CommandExitCode.OK,
            context=mismatched_ctx,
            findings=(_established(), _verified(), _version()),
            error=None,
        )


def test_naive_started_at_serializes_as_utc() -> None:
    result = VersionCommandResult(
        started_at=datetime(2026, 1, 15, 12, 0, 0),
        duration_ms=0,
        app_version="0.1.0",
    )
    payload = result.model_dump(mode="json")
    assert payload["started_at"].endswith("Z")
