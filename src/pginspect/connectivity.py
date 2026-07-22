"""Connect-test stage builders (run_connect_test added in Task 11)."""

from __future__ import annotations

from datetime import datetime, timezone

from pginspect._version import get_app_version
from pginspect.exit_codes import resolve_completed_exit_code, resolve_failed_exit_code
from pginspect.models.context import ConnectionContext
from pginspect.models.enums import CommandOutcome, ExecutionErrorCategory
from pginspect.models.execution_error import ExecutionError
from pginspect.models.finding import (
    ConnectionEstablishedFinding,
    ConnectionFailedFinding,
    Finding,
    SessionSafetyMisconfiguredFinding,
    SessionSafetyVerifiedFinding,
)
from pginspect.models.result import ConnectTestCommandResult, VersionCommandResult


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_version_result(*, duration_ms: int = 0) -> VersionCommandResult:
    return VersionCommandResult(
        started_at=_now(),
        duration_ms=duration_ms,
        app_version=get_app_version(),
    )


def build_connect_operational_failure(
    *,
    finding: ConnectionFailedFinding,
    error: ExecutionError,
    started_at: datetime,
    duration_ms: int,
) -> ConnectTestCommandResult:
    if error.category is not ExecutionErrorCategory.CONNECTION:
        raise ValueError("operational connect failure requires error.category=connection")
    return ConnectTestCommandResult(
        started_at=started_at,
        duration_ms=duration_ms,
        app_version=get_app_version(),
        outcome=CommandOutcome.FAILED,
        exit_code=resolve_failed_exit_code(error),
        context=None,
        findings=(finding,),
        error=error,
    )


def build_preconnect_internal_failure(
    *,
    error: ExecutionError,
    started_at: datetime,
    duration_ms: int,
) -> ConnectTestCommandResult:
    if error.category is not ExecutionErrorCategory.INTERNAL:
        raise ValueError("preconnect internal failure requires error.category=internal")
    return ConnectTestCommandResult(
        started_at=started_at,
        duration_ms=duration_ms,
        app_version=get_app_version(),
        outcome=CommandOutcome.FAILED,
        exit_code=resolve_failed_exit_code(error),
        context=None,
        findings=(),
        error=error,
    )


def build_session_safety_misconfigured(
    *,
    established: ConnectionEstablishedFinding,
    misconfigured: SessionSafetyMisconfiguredFinding,
    started_at: datetime,
    duration_ms: int,
) -> ConnectTestCommandResult:
    findings: tuple[Finding, ...] = (established, misconfigured)
    return ConnectTestCommandResult(
        started_at=started_at,
        duration_ms=duration_ms,
        app_version=get_app_version(),
        outcome=CommandOutcome.COMPLETED,
        exit_code=resolve_completed_exit_code(findings),
        context=None,
        findings=findings,
        error=None,
    )


def build_post_connection_failure(
    *,
    established: ConnectionEstablishedFinding,
    safety_verified: SessionSafetyVerifiedFinding,
    error: ExecutionError,
    started_at: datetime,
    duration_ms: int,
) -> ConnectTestCommandResult:
    findings: tuple[Finding, ...] = (established, safety_verified)
    return ConnectTestCommandResult(
        started_at=started_at,
        duration_ms=duration_ms,
        app_version=get_app_version(),
        outcome=CommandOutcome.FAILED,
        exit_code=resolve_failed_exit_code(error),
        context=None,
        findings=findings,
        error=error,
    )


def build_completed_connect_test(
    *,
    established: ConnectionEstablishedFinding,
    safety_verified: SessionSafetyVerifiedFinding,
    version_finding: Finding,
    context: ConnectionContext,
    started_at: datetime,
    duration_ms: int,
) -> ConnectTestCommandResult:
    findings: tuple[Finding, ...] = (established, safety_verified, version_finding)
    return ConnectTestCommandResult(
        started_at=started_at,
        duration_ms=duration_ms,
        app_version=get_app_version(),
        outcome=CommandOutcome.COMPLETED,
        exit_code=resolve_completed_exit_code(findings),
        context=context,
        findings=findings,
        error=None,
    )
