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
from pginspect.models.finding import (
    Finding,
    finding_adapter,
)

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
    "Finding",
    "FindingId",
    "FindingStatus",
    "KnownExtensionSnapshot",
    "PrivilegeSnapshot",
    "SessionSafetyMisconfigurationCategory",
    "Severity",
    "VersionSupportStatus",
    "finding_adapter",
]
