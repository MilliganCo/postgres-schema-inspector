"""Impact statement card contracts (schema 0.1, design section 4.3 / 4.4)."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from pginspect.impact.models.enums import (
    AnalysisStatus,
    ConfidenceLevel,
    ExecutionPrediction,
    ImpactRole,
    ImpactScaleConfidence,
    LockMode,
    NoOpReason,
    ObjectKind,
    PhysicalTriState,
    Risk,
)
from pginspect.models.base import PublicModel


class ImpactConfidence(PublicModel):
    lock: ConfidenceLevel
    rewrite: ConfidenceLevel
    execution: ConfidenceLevel
    dependencies: ConfidenceLevel
    impact_scale: ImpactScaleConfidence


class SaferRollout(PublicModel):
    steps: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()


class AffectedObjectRef(PublicModel):
    """`schema_` is the Python attribute; the wire/alias name is `schema`
    (matches design section 4.3) since `schema` shadows a deprecated
    `pydantic.BaseModel` attribute.
    """

    model_config = ConfigDict(populate_by_name=True)

    object_kind: ObjectKind
    identity: str
    schema_: str | None = Field(alias="schema")
    name: str
    parent_identity: str | None
    impact_role: ImpactRole
    detail: str | None


class ImpactStatementCard(PublicModel):
    statement_index: int
    start_line: int
    end_line: int
    statement_fingerprint: str
    sanitized_preview: str

    analysis_status: AnalysisStatus
    execution_prediction: ExecutionPrediction
    no_op_reason: NoOpReason | None

    risk: Risk
    confidence: ImpactConfidence

    lock: LockMode
    table_rewrite: PhysicalTriState
    table_scan: PhysicalTriState
    index_rebuild: PhysicalTriState

    affected_objects: tuple[AffectedObjectRef, ...] = ()
    why: tuple[str, ...] = ()
    safer_rollout: SaferRollout | None = None
    limitations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
