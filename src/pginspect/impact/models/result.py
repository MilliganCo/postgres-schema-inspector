"""ImpactCommandResult contract (schema 0.1, design section 4.3 / 4.5 / 4.6)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, model_validator

from pginspect.impact.models.card import ImpactConfidence, ImpactStatementCard
from pginspect.impact.models.enums import (
    AnalysisStage,
    ExecutionPrediction,
    ImpactPreflightCheckStatus,
    Outcome,
    PreflightStatus,
    Risk,
)
from pginspect.impact.models.evidence import ImpactEvidence
from pginspect.models.base import PublicModel
from pginspect.models.execution_error import ExecutionError

__all__ = [
    "ImpactCommandResult",
    "ImpactConfidence",
    "ImpactConnectionContext",
    "ImpactInputMeta",
    "ImpactPreflight",
    "ImpactPreflightCheck",
    "ImpactSnapshot",
    "ImpactSummary",
    "impact_command_result_adapter",
]

_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{16}$")
_MAX_PREVIEW_CODEPOINTS = 240

_RISK_PRIORITY: dict[Risk, int] = {
    Risk.NOT_APPLICABLE: 0,
    Risk.SAFE: 1,
    Risk.WARNING: 2,
    Risk.CRITICAL: 3,
}

_STAGES_WITH_CLASSIFICATION_COMPLETE = frozenset(
    {
        AnalysisStage.RESOLVE,
        AnalysisStage.CATALOG,
        AnalysisStage.RULES,
        AnalysisStage.COMPLETE,
    }
)


class ImpactInputMeta(PublicModel):
    path_basename: str
    source_statement_count: Annotated[int, Field(ge=0)]
    card_count: Annotated[int, Field(ge=0)]
    control_statement_count: Annotated[int, Field(ge=0)]


class ImpactPreflightCheck(PublicModel):
    id: str
    status: ImpactPreflightCheckStatus
    detail: str


class ImpactPreflight(PublicModel):
    status: PreflightStatus
    analysis_stage_reached: AnalysisStage
    checks: tuple[ImpactPreflightCheck, ...] = ()
    limitations: tuple[str, ...] = ()


class ImpactSnapshot(PublicModel):
    catalog_snapshot_at: datetime
    metrics_observed_at: datetime | None
    metrics_consistency: Literal["best_effort"]
    server_version_num: int


class ImpactSummary(PublicModel):
    overall_risk: Risk
    critical_count: Annotated[int, Field(ge=0)]
    warning_count: Annotated[int, Field(ge=0)]
    safe_count: Annotated[int, Field(ge=0)]
    not_applicable_count: Annotated[int, Field(ge=0)]
    would_fail_count: Annotated[int, Field(ge=0)]
    may_fail_count: Annotated[int, Field(ge=0)]
    unsupported_count: Annotated[int, Field(ge=0)]
    no_op_count: Annotated[int, Field(ge=0)]
    analyzed_count: Annotated[int, Field(ge=0)]
    incomplete: bool


class ImpactConnectionContext(PublicModel):
    server_version: str
    server_version_num: int
    server_major: int
    database: str
    role: str
    session_user: str
    current_schema: str | None
    search_path_raw: str
    standard_conforming_strings: str
    server_encoding: str
    client_encoding: str
    transaction_isolation: str
    transaction_read_only: str
    in_recovery: bool
    max_identifier_length: int


class ImpactCommandResult(PublicModel):
    schema_version: Literal["0.1"] = "0.1"
    command: Literal["impact"] = "impact"
    outcome: Outcome
    exit_code: Literal[0, 1, 2, 3, 5]
    started_at: datetime
    duration_ms: Annotated[int, Field(ge=0)]
    app_version: str

    input: ImpactInputMeta
    connection_context: ImpactConnectionContext | None
    preflight: ImpactPreflight
    snapshot: ImpactSnapshot | None
    summary: ImpactSummary
    statements: tuple[ImpactStatementCard, ...]
    evidence: tuple[ImpactEvidence, ...]
    error: ExecutionError | None

    @model_validator(mode="after")
    def _validate_started_at_is_utc(self) -> ImpactCommandResult:
        if self.started_at.tzinfo is None or self.started_at.utcoffset() != timedelta(0):
            raise ValueError("started_at must be a timezone-aware UTC datetime")
        return self

    @model_validator(mode="after")
    def _validate_outcome_invariants(self) -> ImpactCommandResult:
        if self.outcome is Outcome.COMPLETED:
            if self.exit_code not in (0, 1, 2):
                raise ValueError("completed outcome requires exit_code in {0,1,2}")
            if self.error is not None:
                raise ValueError("completed outcome requires error=null")
            if self.summary.incomplete:
                raise ValueError("completed outcome requires summary.incomplete=false")
            for card in self.statements:
                if card.analysis_status.value.startswith("unsupported_"):
                    raise ValueError(
                        "completed outcome forbids cards with unsupported_* analysis_status"
                    )
        elif self.outcome is Outcome.INCOMPLETE:
            if self.exit_code != 3:
                raise ValueError("incomplete outcome requires exit_code=3")
            if not self.summary.incomplete:
                raise ValueError("incomplete outcome requires summary.incomplete=true")
        elif self.outcome is Outcome.FAILED:
            if self.exit_code not in (3, 5):
                raise ValueError("failed outcome requires exit_code in {3,5}")
            if self.error is None:
                raise ValueError("failed outcome requires error")
            if self.statements:
                raise ValueError("failed outcome requires statements=()")
            if self.summary.overall_risk is not Risk.NOT_APPLICABLE:
                raise ValueError("failed outcome requires summary.overall_risk=not_applicable")
            if not self.summary.incomplete:
                raise ValueError("failed outcome requires summary.incomplete=true")
        return self

    @model_validator(mode="after")
    def _validate_card_level_invariants(self) -> ImpactCommandResult:
        seen_indexes: list[int] = []
        for card in self.statements:
            if card.execution_prediction is ExecutionPrediction.NO_OP:
                if card.no_op_reason is None:
                    raise ValueError("execution_prediction=no_op requires no_op_reason to be set")
            elif card.no_op_reason is not None:
                raise ValueError("no_op_reason must be null unless execution_prediction=no_op")

            if card.analysis_status.value.startswith("unsupported_"):
                if card.execution_prediction is not ExecutionPrediction.NOT_EVALUATED:
                    raise ValueError(
                        "unsupported_* analysis_status requires execution_prediction=not_evaluated"
                    )
                if card.risk is not Risk.NOT_APPLICABLE:
                    raise ValueError("unsupported_* analysis_status requires risk=not_applicable")

            if _FINGERPRINT_RE.match(card.statement_fingerprint) is None:
                raise ValueError(
                    f"statement_fingerprint {card.statement_fingerprint!r} "
                    "does not match ^sha256:[0-9a-f]{16}$"
                )

            if len(card.sanitized_preview) > _MAX_PREVIEW_CODEPOINTS:
                raise ValueError("sanitized_preview exceeds 240 Unicode code points")

            if card.statement_index < 1:
                raise ValueError("statement_index must be >= 1")
            seen_indexes.append(card.statement_index)

        if len(set(seen_indexes)) != len(seen_indexes):
            raise ValueError("statement_index values must be unique")
        if seen_indexes != sorted(seen_indexes):
            raise ValueError("statements must be strictly ascending by statement_index")
        return self

    @model_validator(mode="after")
    def _validate_evidence_integrity(self) -> ImpactCommandResult:
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("evidence_id values must be unique")
        evidence_id_set = set(evidence_ids)

        referenced: set[str] = set()
        for card in self.statements:
            for ref in card.evidence_refs:
                if ref not in evidence_id_set:
                    raise ValueError(f"evidence_ref {ref!r} not found in evidence")
                referenced.add(ref)

        if self.statements and (evidence_id_set - referenced):
            raise ValueError("every evidence entry must be referenced by at least one card")
        return self

    @model_validator(mode="after")
    def _validate_statement_counts(self) -> ImpactCommandResult:
        if self.input.card_count != len(self.statements):
            raise ValueError("input.card_count must equal len(statements)")
        if self.input.source_statement_count < self.input.control_statement_count:
            raise ValueError(
                "input.source_statement_count must be >= input.control_statement_count"
            )
        classification_complete = (
            self.preflight.analysis_stage_reached in _STAGES_WITH_CLASSIFICATION_COMPLETE
            and self.outcome is not Outcome.FAILED
        )
        if classification_complete:
            expected = self.input.card_count + self.input.control_statement_count
            if self.input.source_statement_count != expected:
                raise ValueError(
                    "source_statement_count must equal card_count + control_statement_count "
                    "once classification is complete"
                )
        return self

    @model_validator(mode="after")
    def _validate_risk_summary(self) -> ImpactCommandResult:
        summary = self.summary
        total = (
            summary.critical_count
            + summary.warning_count
            + summary.safe_count
            + summary.not_applicable_count
        )
        if total != len(self.statements):
            raise ValueError(
                "critical_count + warning_count + safe_count + not_applicable_count "
                "must equal len(statements)"
            )
        if self.statements:
            observed_max = max(
                (card.risk for card in self.statements),
                key=lambda risk: _RISK_PRIORITY[risk],
            )
            if summary.overall_risk is not observed_max:
                raise ValueError("summary.overall_risk must equal the max observed card risk")
        return self


impact_command_result_adapter: TypeAdapter[ImpactCommandResult] = TypeAdapter(ImpactCommandResult)
