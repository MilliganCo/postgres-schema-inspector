"""Extra text-renderer and misc small-module coverage."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

import pytest

from pginspect.connectivity import (
    build_completed_connect_test,
    build_connect_operational_failure,
    build_post_connection_failure,
    build_session_safety_misconfigured,
)
from pginspect.exit_codes import resolve_failed_exit_code
from pginspect.models.context import (
    ConnectionContext,
    ConnectionTargetContext,
    KnownExtensionSnapshot,
    PrivilegeSnapshot,
)
from pginspect.models.enums import (
    ClassificationSource,
    ConnectionTargetSource,
    ExecutionErrorCategory,
    ExecutionErrorCode,
    ExtensionAvailability,
    SessionSafetyMisconfigurationCategory,
    VersionSupportStatus,
)
from pginspect.models.execution_error import DebugFrame, DebugPayload, ExecutionError
from pginspect.models.finding import (
    ConnectionEstablishedEvidence,
    ConnectionEstablishedFinding,
    ConnectionFailedEvidence,
    ConnectionFailedFinding,
    ConnectionFindingScope,
    ServerVersionExperimentalEvidence,
    ServerVersionExperimentalFinding,
    ServerVersionUnsupportedEvidence,
    ServerVersionUnsupportedFinding,
    SessionSafetyExpectedState,
    SessionSafetyMisconfiguredEvidence,
    SessionSafetyMisconfiguredFinding,
    SessionSafetyObservedState,
    SessionSafetyVerifiedEvidence,
    SessionSafetyVerifiedFinding,
)
from pginspect.renderers.text import render_text, render_text_debug
from pginspect.version_policy import server_major_from_num, server_major_label


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


def _context(
    *, support: VersionSupportStatus = VersionSupportStatus.SUPPORTED
) -> ConnectionContext:
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


def test_render_text_rejects_unknown_type() -> None:
    with pytest.raises(TypeError, match="unsupported CommandResult"):
        render_text(object())  # type: ignore[arg-type]


def test_render_text_debug_causal_chain() -> None:
    failed = build_connect_operational_failure(
        finding=ConnectionFailedFinding(
            title="Could not connect to PostgreSQL",
            scope=_scope(),
            evidence=ConnectionFailedEvidence(
                category="authentication_failed",
                classification_source=ClassificationSource.SQLSTATE,
                sqlstate="28P01",
            ),
        ),
        error=ExecutionError(
            code=ExecutionErrorCode.AUTHENTICATION_FAILED,
            category=ExecutionErrorCategory.CONNECTION,
            message="PostgreSQL authentication failed.",
            retryable=False,
            debug=DebugPayload(
                exception_type="ConnectAuthenticationError",
                causal_chain_types=("OperationalError", "Exception"),
                frames=(DebugFrame(module="pginspect.connection", function="open", line=1),),
            ),
        ),
        started_at=datetime.now(timezone.utc),
        duration_ms=1,
    )
    debug = render_text_debug(failed)
    assert debug is not None
    assert "causal_chain: OperationalError, Exception" in debug


def test_render_misconfigured_with_observed_timeouts() -> None:
    result = build_session_safety_misconfigured(
        established=_established(),
        misconfigured=SessionSafetyMisconfiguredFinding(
            title="Diagnostic session safety settings are not active",
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
                    transaction_read_only=True,
                    statement_timeout_ms=999,
                    lock_timeout_ms=2000,
                    idle_in_transaction_session_timeout_ms=15000,
                    search_path=("pg_catalog",),
                ),
                sqlstate=None,
            ),
        ),
        started_at=datetime.now(timezone.utc),
        duration_ms=1,
    )
    text = render_text(result)
    assert "Session safety: MISCONFIGURED" in text
    assert "Expected timeouts:" in text
    assert "Observed timeouts: statement=999ms" in text


def test_render_unknown_session_safety_and_post_error() -> None:
    result = build_post_connection_failure(
        established=_established(),
        safety_verified=_verified(),
        error=ExecutionError(
            code=ExecutionErrorCode.INTERNAL_FAILURE,
            category=ExecutionErrorCategory.INTERNAL,
            message="pginspect failed due to an internal error.",
            retryable=False,
        ),
        started_at=datetime.now(timezone.utc),
        duration_ms=1,
    )
    # Drop verified finding to hit "Session safety: unknown" via model_construct bypass.
    unknown = result.model_copy(update={"findings": (_established(),)})
    text = render_text(unknown)
    assert "Session safety: unknown" in text
    assert "Error: pginspect failed due to an internal error." in text


def test_render_version_finding_with_summary() -> None:
    ctx = _context(support=VersionSupportStatus.UNSUPPORTED_OLDER).model_copy(
        update={
            "server_version": "13.8",
            "server_version_num": 130008,
            "server_major": 13,
            "server_major_label": "13",
        }
    )
    result = build_completed_connect_test(
        established=_established(),
        safety_verified=_verified(),
        version_finding=ServerVersionUnsupportedFinding(
            title="PostgreSQL server version is unsupported",
            summary="Upgrade to a supported major.",
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
        ),
        context=ctx,
        started_at=datetime.now(timezone.utc),
        duration_ms=1,
    )
    text = render_text(result)
    assert "Finding: PostgreSQL server version is unsupported" in text
    assert "Upgrade to a supported major." in text


def test_render_experimental_finding_title() -> None:
    ctx = _context(support=VersionSupportStatus.EXPERIMENTAL).model_copy(
        update={
            "server_version": "19beta2",
            "server_version_num": 190000,
            "server_major": 19,
            "server_major_label": "19",
        }
    )
    result = build_completed_connect_test(
        established=_established(),
        safety_verified=_verified(),
        version_finding=ServerVersionExperimentalFinding(
            title="PostgreSQL server version is experimental",
            scope=_scope(),
            evidence=ServerVersionExperimentalEvidence(
                server_version="19beta2",
                server_version_num=190000,
                server_major=19,
                server_major_label="19",
                version_support="experimental",
                supported_majors=(14, 15, 16, 17, 18),
                max_tested_stable_major=18,
                tested_prerelease_majors=(19,),
            ),
        ),
        context=ctx,
        started_at=datetime.now(timezone.utc),
        duration_ms=1,
    )
    assert "Finding: PostgreSQL server version is experimental" in render_text(result)


def test_server_major_label_legacy_and_unknown() -> None:
    assert server_major_from_num(90624) is None
    assert server_major_label(90624, "9.6.24") == "9.6"
    assert server_major_label(80400, "8.4.0") == "8.4.0"
    assert server_major_label(1, "") == "unknown"
    assert server_major_label(180004, "18.4") == "18"


def test_resolve_failed_unsupported_category() -> None:
    error = ExecutionError.model_construct(
        code=ExecutionErrorCode.INTERNAL_FAILURE,
        category="not-a-real-category",
        message="x",
        retryable=False,
    )
    with pytest.raises(ValueError, match="Unsupported execution error category"):
        resolve_failed_exit_code(error)  # type: ignore[arg-type]


def test_get_app_version_package_not_found() -> None:
    with patch("pginspect._version.version", side_effect=PackageNotFoundError("missing")):
        from pginspect._version import get_app_version

        assert get_app_version() == "0.0.0+unknown"


def test_tls_signal_maps_to_tls_error() -> None:
    from pginspect.config import ConnectionConfig
    from pginspect.connection import _connect
    from pginspect.exceptions import ConnectTlsError
    import psycopg

    class SslDriverError(psycopg.Error):
        pass

    with patch("pginspect.connection.psycopg.connect", side_effect=SslDriverError()):
        with pytest.raises(ConnectTlsError):
            _connect(ConnectionConfig())


def test_open_connection_swallows_close_errors() -> None:
    from pginspect.config import ConnectionConfig
    from pginspect.connection import open_connection

    mock_conn = MagicMock()
    mock_conn.close.side_effect = RuntimeError("close failed")
    with patch("pginspect.connection.psycopg.connect", return_value=mock_conn):
        with open_connection(ConnectionConfig()) as conn:
            assert conn is mock_conn
    mock_conn.close.assert_called_once()
