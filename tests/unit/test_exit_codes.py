"""Tests for exit-code resolvers."""

from __future__ import annotations

from pginspect.exit_codes import resolve_completed_exit_code, resolve_failed_exit_code
from pginspect.models.context import ConnectionTargetContext
from pginspect.models.enums import (
    ClassificationSource,
    CommandExitCode,
    ConnectionTargetSource,
    ExecutionErrorCategory,
    ExecutionErrorCode,
    FindingId,
    SessionSafetyMisconfigurationCategory,
    Severity,
)
from pginspect.models.execution_error import ExecutionError
from pginspect.models.finding import (
    ConnectionEstablishedEvidence,
    ConnectionEstablishedFinding,
    ConnectionFindingScope,
    SessionSafetyExpectedState,
    SessionSafetyMisconfiguredEvidence,
    SessionSafetyMisconfiguredFinding,
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


def test_resolve_completed_critical_over_warning() -> None:
    established = ConnectionEstablishedFinding(
        title="ok",
        scope=_scope(),
        evidence=ConnectionEstablishedEvidence(tls_used=None),
    )
    misconfigured = SessionSafetyMisconfiguredFinding(
        title="bad",
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
    assert resolve_completed_exit_code((established, misconfigured)) is CommandExitCode.CRITICAL


def test_resolve_completed_ignores_passed() -> None:
    verified = SessionSafetyVerifiedFinding(
        title="ok",
        scope=_scope(),
        evidence=SessionSafetyVerifiedEvidence(
            default_transaction_read_only=True,
            transaction_read_only=True,
            statement_timeout_ms=15000,
            lock_timeout_ms=2000,
            idle_in_transaction_session_timeout_ms=15000,
            search_path=("pg_catalog",),
            application_name_kind="empty",
            application_name_value=None,
            write_probe="not_run",
            verification_level="settings",
            read_only_scope="postgresql_transaction",
            read_only_is_sandbox=False,
        ),
    )
    assert verified.id is FindingId.CONNECTION_SESSION_SAFETY_VERIFIED
    assert verified.severity is Severity.OK
    assert resolve_completed_exit_code((verified,)) is CommandExitCode.OK


def test_resolve_failed_internal_and_connection() -> None:
    internal = ExecutionError(
        code=ExecutionErrorCode.INTERNAL_FAILURE,
        category=ExecutionErrorCategory.INTERNAL,
        message="pginspect failed due to an internal error.",
        retryable=False,
    )
    conn = ExecutionError(
        code=ExecutionErrorCode.AUTHENTICATION_FAILED,
        category=ExecutionErrorCategory.CONNECTION,
        message="PostgreSQL authentication failed.",
        retryable=False,
        sqlstate="28P01",
        classification_source=ClassificationSource.SQLSTATE,
    )
    assert resolve_failed_exit_code(internal) is CommandExitCode.INTERNAL_FAILURE
    assert resolve_failed_exit_code(conn) is CommandExitCode.OPERATIONAL_FAILURE
