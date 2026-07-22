"""Foundation enums (schema 1.0)."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    OK = "ok"


class FindingStatus(StrEnum):
    TRIGGERED = "triggered"
    PASSED = "passed"


class CommandOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class CommandExitCode(IntEnum):
    OK = 0
    WARNING = 1
    CRITICAL = 2
    OPERATIONAL_FAILURE = 3
    INTERNAL_FAILURE = 5


class FindingId(StrEnum):
    CONNECTION_ESTABLISHED = "connection.established"
    CONNECTION_FAILED = "connection.failed"
    CONNECTION_SERVER_VERSION_SUPPORTED = "connection.server_version_supported"
    CONNECTION_SERVER_VERSION_EXPERIMENTAL = "connection.server_version_experimental"
    CONNECTION_SERVER_VERSION_UNTESTED = "connection.server_version_untested"
    CONNECTION_SERVER_VERSION_UNSUPPORTED = "connection.server_version_unsupported"
    CONNECTION_SESSION_SAFETY_VERIFIED = "connection.session_safety_verified"
    CONNECTION_SESSION_SAFETY_MISCONFIGURED = "connection.session_safety_misconfigured"


class VersionSupportStatus(StrEnum):
    SUPPORTED = "supported"
    EXPERIMENTAL = "experimental"
    UNTESTED_NEWER = "untested_newer"
    UNSUPPORTED_OLDER = "unsupported_older"
    UNSUPPORTED_LEGACY = "unsupported_legacy"


class SessionSafetyMisconfigurationCategory(StrEnum):
    SET_REJECTED = "set_rejected"
    VERIFICATION_MISMATCH = "verification_mismatch"


class ConnectionTargetSource(StrEnum):
    EXPLICIT_CLI_HOST = "explicit_cli_host"
    LIBPQ_RESOLVED_UNKNOWN = "libpq_resolved_unknown"


class ExtensionAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class ExecutionErrorCategory(StrEnum):
    CONNECTION = "connection"
    SESSION = "session"
    OPERATIONAL = "operational"
    INTERNAL = "internal"


class ExecutionErrorCode(StrEnum):
    AUTHENTICATION_FAILED = "authentication_failed"
    NETWORK_UNREACHABLE = "network_unreachable"
    CONNECT_TIMEOUT = "connect_timeout"
    TLS_FAILED = "tls_failed"
    DATABASE_MISSING = "database_missing"
    CONNECTION_FAILED = "connection_failed"
    OPERATIONAL_FAILURE = "operational_failure"
    INTERNAL_FAILURE = "internal_failure"


class ClassificationSource(StrEnum):
    CONNECTION_TIMEOUT_TYPE = "connection_timeout_type"
    SQLSTATE = "sqlstate"
    NEEDS_PASSWORD = "needs_password"
    AUDITED_TLS_SIGNAL = "audited_tls_signal"
    FALLBACK_OTHER = "fallback_other"
    INTERNAL = "internal"
