"""Unit tests for Foundation enums and context/error models."""

from __future__ import annotations

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
    ConnectionTargetSource,
    ExtensionAvailability,
    FindingId,
    Severity,
    VersionSupportStatus,
)
from pginspect.models.execution_error import DebugFrame, DebugPayload, ExecutionError
from pginspect.models.enums import ExecutionErrorCategory, ExecutionErrorCode


def test_severity_rejects_info() -> None:
    with pytest.raises(ValueError):
        Severity("info")


def test_severity_accepts_only_foundation_values() -> None:
    assert set(Severity) == {
        Severity.CRITICAL,
        Severity.WARNING,
        Severity.OK,
    }


def test_known_extension_snapshot_requires_all_four() -> None:
    with pytest.raises(ValidationError):
        KnownExtensionSnapshot(  # type: ignore[call-arg]
            hypopg=ExtensionAvailability.AVAILABLE,
            pg_stat_statements=ExtensionAvailability.UNAVAILABLE,
            pgstattuple=ExtensionAvailability.UNAVAILABLE,
        )


def test_known_extension_snapshot_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        KnownExtensionSnapshot(
            hypopg=ExtensionAvailability.AVAILABLE,
            pg_stat_statements=ExtensionAvailability.UNAVAILABLE,
            pgstattuple=ExtensionAvailability.UNAVAILABLE,
            pg_buffercache=ExtensionAvailability.UNAVAILABLE,
            hypopg_extra=ExtensionAvailability.AVAILABLE,  # type: ignore[call-arg]
        )


def test_connection_context_requires_session_user() -> None:
    target = ConnectionTargetContext(
        explicit_host_fingerprint=None,
        source=ConnectionTargetSource.LIBPQ_RESOLVED_UNKNOWN,
    )
    privileges = PrivilegeSnapshot(
        is_superuser=False,
        can_use_pg_monitor=True,
        can_use_pg_read_all_stats=True,
        can_use_pg_read_all_settings=False,
    )
    extensions = KnownExtensionSnapshot(
        hypopg=ExtensionAvailability.UNAVAILABLE,
        pg_stat_statements=ExtensionAvailability.UNAVAILABLE,
        pgstattuple=ExtensionAvailability.UNAVAILABLE,
        pg_buffercache=ExtensionAvailability.UNAVAILABLE,
    )
    with pytest.raises(ValidationError):
        ConnectionContext(  # type: ignore[call-arg]
            database="shop",
            role="monitor",
            server_version="18.4",
            server_version_num=180004,
            server_major=18,
            server_major_label="18",
            version_support=VersionSupportStatus.SUPPORTED,
            in_recovery=False,
            target=target,
            privileges=privileges,
            extensions=extensions,
        )


def test_execution_error_requires_core_fields() -> None:
    with pytest.raises(ValidationError):
        ExecutionError(  # type: ignore[call-arg]
            message="PostgreSQL authentication failed.",
            retryable=False,
        )


def test_execution_error_round_trip() -> None:
    err = ExecutionError(
        code=ExecutionErrorCode.AUTHENTICATION_FAILED,
        category=ExecutionErrorCategory.CONNECTION,
        message="PostgreSQL authentication failed.",
        retryable=False,
        sqlstate="28P01",
        classification_source=ClassificationSource.SQLSTATE,
        debug=DebugPayload(
            exception_type="psycopg.OperationalError",
            causal_chain_types=("psycopg.OperationalError",),
            frames=(DebugFrame(module="pginspect.connection", function="_connect", line=10),),
        ),
    )
    assert err.code is ExecutionErrorCode.AUTHENTICATION_FAILED
    assert err.debug is not None
    assert len(err.debug.frames) == 1


def test_command_exit_code_excludes_4_and_130() -> None:
    values = {int(code) for code in CommandExitCode}
    assert 4 not in values
    assert 130 not in values
    assert values == {0, 1, 2, 3, 5}


def test_finding_id_has_eight_values() -> None:
    assert len(FindingId) == 8
