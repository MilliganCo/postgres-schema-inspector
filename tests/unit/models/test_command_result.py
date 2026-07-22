"""Tests for CommandResult builders and validators."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from pginspect.connectivity import (
    build_completed_connect_test,
    build_connect_operational_failure,
    build_session_safety_misconfigured,
    build_version_result,
)
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
    SessionSafetyMisconfigurationCategory,
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
    ServerVersionUnsupportedEvidence,
    ServerVersionUnsupportedFinding,
    SessionSafetyExpectedState,
    SessionSafetyMisconfiguredEvidence,
    SessionSafetyMisconfiguredFinding,
    SessionSafetyObservedState,
    SessionSafetyVerifiedEvidence,
    SessionSafetyVerifiedFinding,
)


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


def _context(support: VersionSupportStatus = VersionSupportStatus.SUPPORTED) -> ConnectionContext:
    return ConnectionContext(
        database="shop",
        role="monitor",
        session_user="monitor",
        server_version="18.4",
        server_version_num=180004,
        server_major=18,
        server_major_label="18",
        version_support=support,
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


def test_version_result_always_exit_0() -> None:
    result = build_version_result()
    assert result.exit_code is CommandExitCode.OK
    assert result.outcome is CommandOutcome.COMPLETED
    assert result.findings == ()


def test_completed_critical_finding_exit_2() -> None:
    misconfigured = SessionSafetyMisconfiguredFinding(
        title="Diagnostic session safety settings are not active",
        scope=_scope(),
        evidence=SessionSafetyMisconfiguredEvidence(
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
            sqlstate=None,
        ),
    )
    result = build_session_safety_misconfigured(
        established=_established(),
        misconfigured=misconfigured,
        started_at=datetime.now(timezone.utc),
        duration_ms=10,
    )
    assert result.exit_code == 2
    assert result.outcome.value == "completed"
    assert result.error is None


def test_connection_failed_requires_exit_3_and_matching_error_code() -> None:
    finding = ConnectionFailedFinding(
        title="Could not connect to PostgreSQL",
        scope=_scope(),
        evidence=ConnectionFailedEvidence(
            category="authentication_failed",
            classification_source=ClassificationSource.SQLSTATE,
            sqlstate="28P01",
        ),
    )
    error = ExecutionError(
        code=ExecutionErrorCode.AUTHENTICATION_FAILED,
        category=ExecutionErrorCategory.CONNECTION,
        message="PostgreSQL authentication failed.",
        retryable=False,
        sqlstate="28P01",
        classification_source=ClassificationSource.SQLSTATE,
    )
    result = build_connect_operational_failure(
        finding=finding,
        error=error,
        started_at=datetime.now(timezone.utc),
        duration_ms=5,
    )
    assert result.exit_code == 3
    assert result.outcome is CommandOutcome.FAILED
    assert result.context is None


def test_failed_outcome_ignores_ok_finding_severities() -> None:
    from pginspect.connectivity import build_post_connection_failure

    error = ExecutionError(
        code=ExecutionErrorCode.INTERNAL_FAILURE,
        category=ExecutionErrorCategory.INTERNAL,
        message="pginspect failed due to an internal error.",
        retryable=False,
    )
    result = build_post_connection_failure(
        established=_established(),
        safety_verified=_verified(),
        error=error,
        started_at=datetime.now(timezone.utc),
        duration_ms=12,
    )
    assert result.exit_code == 5
    assert all(f.severity.value in {"ok"} for f in result.findings)


def test_completed_unsupported_version_exit_2() -> None:
    version = ServerVersionUnsupportedFinding(
        title="PostgreSQL version is unsupported",
        scope=_scope(),
        evidence=ServerVersionUnsupportedEvidence(
            server_version="13.8",
            server_version_num=130008,
            server_major=13,
            server_major_label="13",
            version_support="unsupported_older",
            supported_majors=(14, 15, 16, 17, 18),
            max_tested_stable_major=18,
            tested_prerelease_majors=(19,),
        ),
    )
    ctx = _context(VersionSupportStatus.UNSUPPORTED_OLDER)
    # override version fields to match unsupported
    ctx = ctx.model_copy(
        update={
            "server_version": "13.8",
            "server_version_num": 130008,
            "server_major": 13,
            "server_major_label": "13",
            "version_support": VersionSupportStatus.UNSUPPORTED_OLDER,
        }
    )
    result = build_completed_connect_test(
        established=_established(),
        safety_verified=_verified(),
        version_finding=version,
        context=ctx,
        started_at=datetime.now(timezone.utc),
        duration_ms=20,
    )
    assert result.exit_code == 2


def test_reject_mismatched_exit_on_manual_construct() -> None:
    from pginspect.models.result import ConnectTestCommandResult

    with pytest.raises(ValidationError):
        ConnectTestCommandResult(
            started_at=datetime.now(timezone.utc),
            duration_ms=1,
            app_version="0.1.0",
            outcome=CommandOutcome.COMPLETED,
            exit_code=CommandExitCode.OK,
            context=None,
            findings=(
                _established(),
                SessionSafetyMisconfiguredFinding(
                    title="bad",
                    scope=_scope(),
                    evidence=SessionSafetyMisconfiguredEvidence(
                        category=SessionSafetyMisconfigurationCategory.VERIFICATION_MISMATCH,
                        expected=SessionSafetyExpectedState(
                            default_transaction_read_only=True,
                            transaction_read_only=True,
                            statement_timeout_ms=15000,
                            lock_timeout_ms=2000,
                            idle_in_transaction_session_timeout_ms=15000,
                            search_path=("pg_catalog",),
                        ),
                        observed=SessionSafetyObservedState(
                            default_transaction_read_only=False,
                            transaction_read_only=False,
                            statement_timeout_ms=15000,
                            lock_timeout_ms=2000,
                            idle_in_transaction_session_timeout_ms=15000,
                            search_path=("pg_catalog",),
                        ),
                        sqlstate=None,
                    ),
                ),
            ),
            error=None,
        )


def test_healthy_completed_connect_test() -> None:
    version = ServerVersionSupportedFinding(
        title="PostgreSQL version is supported",
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
    result = build_completed_connect_test(
        established=_established(),
        safety_verified=_verified(),
        version_finding=version,
        context=_context(),
        started_at=datetime.now(timezone.utc),
        duration_ms=15,
    )
    assert result.exit_code == 0
    assert len(result.findings) == 3
