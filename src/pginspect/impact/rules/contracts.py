"""Shared rule-engine contracts (plan Task 6, design sections 3.3 / 3.9).

`RuleVerdict` is the in-process shape every rule engine (TYPE / ADD / DROP)
returns before `ImpactStatementCard` assembly: it carries the semantic
verdict plus the evidence and limitations that justify it, and deliberately
omits card-only presentation fields (`source_span`, `affected_objects`,
`safer_rollout`).

`StatementExitView` is the minimal read-only view `aggregate_exit_code`
needs, so both `RuleVerdict` and `ImpactStatementCard` can be aggregated
without an adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pginspect.impact.models.card import ImpactConfidence
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ExecutionPrediction,
    LockMode,
    NoOpReason,
    PhysicalTriState,
    Risk,
)

AUTHORIZATION_LIMITATION = (
    "Authorization failures are not modeled; analysis assumes sufficient privileges."
)

__all__ = [
    "AUTHORIZATION_LIMITATION",
    "RuleVerdict",
    "StatementExitRow",
    "StatementExitView",
]


@dataclass(frozen=True)
class RuleVerdict:
    rule_key: str
    analysis_status: AnalysisStatus
    execution_prediction: ExecutionPrediction
    risk: Risk
    lock: LockMode
    table_rewrite: PhysicalTriState
    table_scan: PhysicalTriState
    index_rebuild: PhysicalTriState
    confidence: ImpactConfidence
    limitations: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    no_op_reason: NoOpReason | None = None
    why: tuple[str, ...] = ()


class StatementExitView(Protocol):
    @property
    def analysis_status(self) -> AnalysisStatus: ...

    @property
    def execution_prediction(self) -> ExecutionPrediction: ...

    @property
    def risk(self) -> Risk: ...


@dataclass(frozen=True)
class StatementExitRow:
    """Concrete `StatementExitView` for callers that hold no card or verdict."""

    analysis_status: AnalysisStatus
    execution_prediction: ExecutionPrediction
    risk: Risk
