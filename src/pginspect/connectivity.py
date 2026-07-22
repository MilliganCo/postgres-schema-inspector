"""Connect-test stage builders and run_connect_test orchestration."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Literal

from pginspect._version import get_app_version
from pginspect.capabilities import DiscoveredCapabilities, discover_capabilities
from pginspect.config import ConnectTestConfig, ConnectionConfig
from pginspect.connection import open_connection
from pginspect.context_builder import build_connection_context, build_target_context
from pginspect.error_catalog import public_connect_message, retryable_for
from pginspect.exceptions import (
    PginspectConnectError,
    PginspectInternalError,
    SessionSafetyError,
)
from pginspect.exit_codes import resolve_completed_exit_code, resolve_failed_exit_code
from pginspect.models.context import ConnectionContext
from pginspect.models.enums import (
    ClassificationSource,
    CommandOutcome,
    ExecutionErrorCategory,
    ExecutionErrorCode,
    VersionSupportStatus,
)
from pginspect.models.execution_error import DebugPayload, ExecutionError
from pginspect.models.finding import (
    ConnectionEstablishedEvidence,
    ConnectionEstablishedFinding,
    ConnectionFailedEvidence,
    ConnectionFailedFinding,
    ConnectionFindingScope,
    Finding,
    ServerVersionExperimentalEvidence,
    ServerVersionExperimentalFinding,
    ServerVersionSupportedEvidence,
    ServerVersionSupportedFinding,
    ServerVersionUnsupportedEvidence,
    ServerVersionUnsupportedFinding,
    ServerVersionUntestedEvidence,
    ServerVersionUntestedFinding,
    SessionSafetyMisconfiguredEvidence,
    SessionSafetyMisconfiguredFinding,
    SessionSafetyVerifiedFinding,
)
from pginspect.models.result import ConnectTestCommandResult, VersionCommandResult
from pginspect.session import DiagnosticSession, observe_transport_metadata
from pginspect.version_policy import (
    MAX_TESTED_STABLE_MAJOR,
    SUPPORTED_MAJORS,
    TESTED_PRERELEASE_MAJORS_TUPLE,
    classify_server_version,
)


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


def _scope_for(connection: ConnectionConfig) -> ConnectionFindingScope:
    return ConnectionFindingScope(target=build_target_context(connection))


def _debug_payload(exc: BaseException, *, include_debug: bool) -> DebugPayload | None:
    if not include_debug:
        return None
    frames = getattr(exc, "debug_frames", ()) or ()
    driver_type = getattr(exc, "driver_exception_type", "") or type(exc).__name__
    return DebugPayload(
        exception_type=str(driver_type) or type(exc).__name__,
        causal_chain_types=(),
        frames=tuple(frames),
    )


def _execution_error_from_connect(
    exc: PginspectConnectError,
    *,
    include_debug: bool,
) -> ExecutionError:
    # Session-phase operational codes stay operational category.
    if exc.code is ExecutionErrorCode.OPERATIONAL_FAILURE:
        category = ExecutionErrorCategory.OPERATIONAL
    else:
        category = ExecutionErrorCategory.CONNECTION
    return ExecutionError(
        code=exc.code,
        category=category,
        message=public_connect_message(exc.code),
        retryable=retryable_for(exc.code),
        sqlstate=exc.sqlstate,
        classification_source=exc.classification_source,
        debug=_debug_payload(exc, include_debug=include_debug),
    )


def _execution_error_internal(
    exc: PginspectInternalError,
    *,
    include_debug: bool,
) -> ExecutionError:
    return ExecutionError(
        code=ExecutionErrorCode.INTERNAL_FAILURE,
        category=ExecutionErrorCategory.INTERNAL,
        message=public_connect_message(ExecutionErrorCode.INTERNAL_FAILURE),
        retryable=retryable_for(ExecutionErrorCode.INTERNAL_FAILURE),
        sqlstate=None,
        classification_source=ClassificationSource.INTERNAL,
        debug=_debug_payload(exc, include_debug=include_debug),
    )


def _connection_failed_finding(
    exc: PginspectConnectError,
    scope: ConnectionFindingScope,
) -> ConnectionFailedFinding:
    return ConnectionFailedFinding(
        title="Could not connect to PostgreSQL",
        scope=scope,
        evidence=ConnectionFailedEvidence(
            category=exc.code.value,  # type: ignore[arg-type]
            classification_source=exc.classification_source,
            sqlstate=exc.sqlstate,
        ),
    )


def _established_finding(
    scope: ConnectionFindingScope,
    tls_used: bool | None,
) -> ConnectionEstablishedFinding:
    return ConnectionEstablishedFinding(
        title="PostgreSQL connection established",
        scope=scope,
        evidence=ConnectionEstablishedEvidence(tls_used=tls_used),
    )


def _misconfigured_finding(
    scope: ConnectionFindingScope,
    exc: SessionSafetyError,
) -> SessionSafetyMisconfiguredFinding:
    return SessionSafetyMisconfiguredFinding(
        title="Diagnostic session safety settings are not active",
        scope=scope,
        evidence=SessionSafetyMisconfiguredEvidence(
            category=exc.category,
            expected=exc.expected,
            observed=exc.observed,
            sqlstate=exc.sqlstate,
        ),
    )


def _verified_finding(
    scope: ConnectionFindingScope,
    session: DiagnosticSession,
) -> SessionSafetyVerifiedFinding:
    return SessionSafetyVerifiedFinding(
        title="Diagnostic session safety settings are active",
        scope=scope,
        evidence=session.verification_evidence,
    )


def _version_finding(
    *,
    discovered: DiscoveredCapabilities,
    scope: ConnectionFindingScope,
    support: VersionSupportStatus,
) -> Finding:
    if support is VersionSupportStatus.SUPPORTED:
        return ServerVersionSupportedFinding(
            title="PostgreSQL server version is supported",
            scope=scope,
            evidence=ServerVersionSupportedEvidence(
                server_version=discovered.server_version,
                server_version_num=discovered.server_version_num,
                server_major=discovered.server_major,
                server_major_label=discovered.server_major_label,
                supported_majors=SUPPORTED_MAJORS,
                max_tested_stable_major=MAX_TESTED_STABLE_MAJOR,
                tested_prerelease_majors=TESTED_PRERELEASE_MAJORS_TUPLE,
                version_support="supported",
            ),
        )
    if support is VersionSupportStatus.EXPERIMENTAL:
        return ServerVersionExperimentalFinding(
            title="PostgreSQL server version is experimental",
            scope=scope,
            evidence=ServerVersionExperimentalEvidence(
                server_version=discovered.server_version,
                server_version_num=discovered.server_version_num,
                server_major=discovered.server_major,
                server_major_label=discovered.server_major_label,
                supported_majors=SUPPORTED_MAJORS,
                max_tested_stable_major=MAX_TESTED_STABLE_MAJOR,
                tested_prerelease_majors=TESTED_PRERELEASE_MAJORS_TUPLE,
                version_support="experimental",
            ),
        )
    if support is VersionSupportStatus.UNTESTED_NEWER:
        return ServerVersionUntestedFinding(
            title="PostgreSQL server version is newer than tested",
            scope=scope,
            evidence=ServerVersionUntestedEvidence(
                server_version=discovered.server_version,
                server_version_num=discovered.server_version_num,
                server_major=discovered.server_major,
                server_major_label=discovered.server_major_label,
                supported_majors=SUPPORTED_MAJORS,
                max_tested_stable_major=MAX_TESTED_STABLE_MAJOR,
                tested_prerelease_majors=TESTED_PRERELEASE_MAJORS_TUPLE,
                version_support="untested_newer",
            ),
        )
    unsupported: Literal["unsupported_older", "unsupported_legacy"] = (
        "unsupported_legacy"
        if support is VersionSupportStatus.UNSUPPORTED_LEGACY
        else "unsupported_older"
    )
    return ServerVersionUnsupportedFinding(
        title="PostgreSQL server version is unsupported",
        scope=scope,
        evidence=ServerVersionUnsupportedEvidence(
            server_version=discovered.server_version,
            server_version_num=discovered.server_version_num,
            server_major=discovered.server_major,
            server_major_label=discovered.server_major_label,
            supported_majors=SUPPORTED_MAJORS,
            max_tested_stable_major=MAX_TESTED_STABLE_MAJOR,
            tested_prerelease_majors=TESTED_PRERELEASE_MAJORS_TUPLE,
            version_support=unsupported,
        ),
    )


def _post_connect_operational_result(
    *,
    established: ConnectionEstablishedFinding,
    safety_verified: SessionSafetyVerifiedFinding | None,
    error: ExecutionError,
    started_at: datetime,
    duration_ms: int,
) -> ConnectTestCommandResult:
    if safety_verified is not None:
        return build_post_connection_failure(
            established=established,
            safety_verified=safety_verified,
            error=error,
            started_at=started_at,
            duration_ms=duration_ms,
        )
    # Establish-phase operational: connection opened, safety not verified.
    return ConnectTestCommandResult(
        started_at=started_at,
        duration_ms=duration_ms,
        app_version=get_app_version(),
        outcome=CommandOutcome.FAILED,
        exit_code=resolve_failed_exit_code(error),
        context=None,
        findings=(established,),
        error=error,
    )


def run_connect_test(
    config: ConnectTestConfig,
    *,
    include_debug: bool = False,
) -> ConnectTestCommandResult:
    """Orchestrate connect → DiagnosticSession → capabilities → CommandResult.

    KeyboardInterrupt is not converted; it propagates to the CLI wrapper.
    """
    started_at = _now()
    t0 = time.perf_counter_ns()

    def elapsed_ms() -> int:
        return max(0, (time.perf_counter_ns() - t0) // 1_000_000)

    scope = _scope_for(config.connection)

    try:
        with open_connection(config.connection) as conn:
            tls_used = observe_transport_metadata(conn).tls_used
            established = _established_finding(scope, tls_used)
            safety_verified: SessionSafetyVerifiedFinding | None = None

            try:
                with DiagnosticSession(conn, config.session) as session:
                    tls_used = session.transport_metadata().tls_used
                    established = _established_finding(scope, tls_used)
                    safety_verified = _verified_finding(scope, session)
                    discovered = discover_capabilities(session)
                    context = build_connection_context(discovered, config.connection)
                    support = classify_server_version(
                        discovered.server_version,
                        discovered.server_version_num,
                    )
                    version_finding = _version_finding(
                        discovered=discovered,
                        scope=scope,
                        support=support,
                    )
                    return build_completed_connect_test(
                        established=established,
                        safety_verified=safety_verified,
                        version_finding=version_finding,
                        context=context,
                        started_at=started_at,
                        duration_ms=elapsed_ms(),
                    )
            except SessionSafetyError as exc:
                return build_session_safety_misconfigured(
                    established=established,
                    misconfigured=_misconfigured_finding(scope, exc),
                    started_at=started_at,
                    duration_ms=elapsed_ms(),
                )
            except PginspectConnectError as exc:
                # Remap connection-category codes from session phase to operational.
                if exc.code is ExecutionErrorCode.OPERATIONAL_FAILURE:
                    error = _execution_error_from_connect(exc, include_debug=include_debug)
                elif exc.code in {
                    ExecutionErrorCode.NETWORK_UNREACHABLE,
                    ExecutionErrorCode.CONNECT_TIMEOUT,
                    ExecutionErrorCode.CONNECTION_FAILED,
                    ExecutionErrorCode.TLS_FAILED,
                    ExecutionErrorCode.AUTHENTICATION_FAILED,
                    ExecutionErrorCode.DATABASE_MISSING,
                }:
                    error = ExecutionError(
                        code=ExecutionErrorCode.OPERATIONAL_FAILURE,
                        category=ExecutionErrorCategory.OPERATIONAL,
                        message=public_connect_message(ExecutionErrorCode.OPERATIONAL_FAILURE),
                        retryable=retryable_for(ExecutionErrorCode.OPERATIONAL_FAILURE),
                        sqlstate=exc.sqlstate,
                        classification_source=exc.classification_source,
                        debug=_debug_payload(exc, include_debug=include_debug),
                    )
                else:
                    error = _execution_error_from_connect(exc, include_debug=include_debug)
                return _post_connect_operational_result(
                    established=established,
                    safety_verified=safety_verified,
                    error=error,
                    started_at=started_at,
                    duration_ms=elapsed_ms(),
                )
            except PginspectInternalError as exc:
                error = _execution_error_internal(exc, include_debug=include_debug)
                if safety_verified is not None:
                    return build_post_connection_failure(
                        established=established,
                        safety_verified=safety_verified,
                        error=error,
                        started_at=started_at,
                        duration_ms=elapsed_ms(),
                    )
                return ConnectTestCommandResult(
                    started_at=started_at,
                    duration_ms=elapsed_ms(),
                    app_version=get_app_version(),
                    outcome=CommandOutcome.FAILED,
                    exit_code=resolve_failed_exit_code(error),
                    context=None,
                    findings=(established,),
                    error=error,
                )
    except PginspectConnectError as exc:
        error = _execution_error_from_connect(exc, include_debug=include_debug)
        # Ensure connection-category for connect-time failures.
        if error.category is not ExecutionErrorCategory.CONNECTION:
            error = ExecutionError(
                code=exc.code
                if exc.code is not ExecutionErrorCode.OPERATIONAL_FAILURE
                else ExecutionErrorCode.CONNECTION_FAILED,
                category=ExecutionErrorCategory.CONNECTION,
                message=public_connect_message(
                    exc.code
                    if exc.code is not ExecutionErrorCode.OPERATIONAL_FAILURE
                    else ExecutionErrorCode.CONNECTION_FAILED
                ),
                retryable=retryable_for(
                    exc.code
                    if exc.code is not ExecutionErrorCode.OPERATIONAL_FAILURE
                    else ExecutionErrorCode.CONNECTION_FAILED
                ),
                sqlstate=exc.sqlstate,
                classification_source=exc.classification_source,
                debug=error.debug,
            )
        finding = _connection_failed_finding(exc, scope)
        # Align finding evidence category with error.code when remapped.
        if finding.evidence.category != error.code.value:
            finding = ConnectionFailedFinding(
                title=finding.title,
                scope=scope,
                evidence=ConnectionFailedEvidence(
                    category=error.code.value,  # type: ignore[arg-type]
                    classification_source=exc.classification_source,
                    sqlstate=exc.sqlstate,
                ),
            )
        return build_connect_operational_failure(
            finding=finding,
            error=error,
            started_at=started_at,
            duration_ms=elapsed_ms(),
        )
    except PginspectInternalError as exc:
        return build_preconnect_internal_failure(
            error=_execution_error_internal(exc, include_debug=include_debug),
            started_at=started_at,
            duration_ms=elapsed_ms(),
        )
    except Exception as exc:
        # Invalid objects / unexpected failures reaching orchestration → internal 5.
        wrapped = PginspectInternalError(
            "unexpected error in run_connect_test",
            driver_exception_type=type(exc).__name__,
        )
        return build_preconnect_internal_failure(
            error=_execution_error_internal(wrapped, include_debug=include_debug),
            started_at=started_at,
            duration_ms=elapsed_ms(),
        )
