"""Public models package."""

from __future__ import annotations

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
    FindingId,
    FindingStatus,
    SessionSafetyMisconfigurationCategory,
    Severity,
    VersionSupportStatus,
)
from pginspect.models.execution_error import DebugFrame, DebugPayload, ExecutionError

__all__ = [
    "ClassificationSource",
    "CommandExitCode",
    "CommandOutcome",
    "ConnectionContext",
    "ConnectionTargetContext",
    "ConnectionTargetSource",
    "DebugFrame",
    "DebugPayload",
    "ExecutionError",
    "ExecutionErrorCategory",
    "ExecutionErrorCode",
    "ExtensionAvailability",
    "FindingId",
    "FindingStatus",
    "KnownExtensionSnapshot",
    "PrivilegeSnapshot",
    "SessionSafetyMisconfigurationCategory",
    "Severity",
    "VersionSupportStatus",
]
