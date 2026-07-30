"""Public impact model contracts (schema 0.1)."""

from __future__ import annotations

from pginspect.impact.models.card import (
    AffectedObjectRef,
    ImpactConfidence,
    ImpactStatementCard,
    SaferRollout,
)
from pginspect.impact.models.enums import (
    AnalysisStage,
    AnalysisStatus,
    ConfidenceLevel,
    EvidenceKind,
    ExecutionPrediction,
    ImpactPreflightCheckStatus,
    ImpactRole,
    ImpactScaleConfidence,
    LockMode,
    NoOpReason,
    ObjectKind,
    Outcome,
    PhysicalTriState,
    PreflightStatus,
    Risk,
)
from pginspect.impact.models.evidence import ImpactEvidence
from pginspect.impact.models.result import (
    ImpactCommandResult,
    ImpactConnectionContext,
    ImpactInputMeta,
    ImpactPreflight,
    ImpactPreflightCheck,
    ImpactSnapshot,
    ImpactSummary,
    impact_command_result_adapter,
)
from pginspect.impact.models.scalars import JSONScalar

__all__ = [
    "AffectedObjectRef",
    "AnalysisStage",
    "AnalysisStatus",
    "ConfidenceLevel",
    "EvidenceKind",
    "ExecutionPrediction",
    "ImpactCommandResult",
    "ImpactConfidence",
    "ImpactConnectionContext",
    "ImpactEvidence",
    "ImpactInputMeta",
    "ImpactPreflight",
    "ImpactPreflightCheck",
    "ImpactPreflightCheckStatus",
    "ImpactRole",
    "ImpactScaleConfidence",
    "ImpactSnapshot",
    "ImpactStatementCard",
    "ImpactSummary",
    "JSONScalar",
    "LockMode",
    "NoOpReason",
    "ObjectKind",
    "Outcome",
    "PhysicalTriState",
    "PreflightStatus",
    "Risk",
    "SaferRollout",
    "impact_command_result_adapter",
]
