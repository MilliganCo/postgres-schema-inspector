from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pginspect.impact.models.card import ImpactStatementCard
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ExecutionPrediction,
    LockMode,
    Outcome,
    PhysicalTriState,
    Risk,
)
from pginspect.impact.models.evidence import ImpactEvidence
from pginspect.impact.models.result import (
    ImpactCommandResult,  # noqa: F401  (re-exported for tests importing via conftest)
    ImpactConfidence,
    ImpactInputMeta,
    ImpactPreflight,
    ImpactSummary,
)


AUTH_LIMIT = "Authorization failures are not modeled; analysis assumes sufficient privileges."


@pytest.fixture
def one_evidence() -> ImpactEvidence:
    return ImpactEvidence(
        evidence_id="rule:add.nullable.no_default",
        kind="semantic_rule",
        summary="nullable add without default",
        attributes={"rule_key": "add.nullable.no_default"},
    )


@pytest.fixture
def one_analyzed_card(one_evidence: ImpactEvidence) -> ImpactStatementCard:
    return ImpactStatementCard(
        statement_index=1,
        start_line=1,
        end_line=1,
        statement_fingerprint="sha256:0123456789abcdef",
        sanitized_preview="ALTER TABLE t ADD COLUMN note text",
        analysis_status=AnalysisStatus.ANALYZED,
        execution_prediction=ExecutionPrediction.APPLIES,
        no_op_reason=None,
        risk=Risk.WARNING,
        confidence=ImpactConfidence(
            lock="high",
            rewrite="high",
            execution="high",
            dependencies="high",
            impact_scale="medium",
        ),
        lock=LockMode.ACCESS_EXCLUSIVE_LOCK,
        table_rewrite=PhysicalTriState.NO,
        table_scan=PhysicalTriState.NO,
        index_rebuild=PhysicalTriState.NO,
        affected_objects=(),
        why=("catalog DDL semantics: metadata-only add",),
        safer_rollout={"steps": (), "assumptions": (), "preconditions": ()},
        limitations=(AUTH_LIMIT,),
        evidence_refs=(one_evidence.evidence_id,),
    )


@pytest.fixture
def minimal_completed_kwargs(one_analyzed_card, one_evidence) -> dict:
    return {
        "schema_version": "0.1",
        "command": "impact",
        "outcome": Outcome.COMPLETED,
        "exit_code": 1,
        "started_at": datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC),
        "duration_ms": 10,
        "app_version": "0.0.0",
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=1,
            card_count=1,
            control_statement_count=0,
        ),
        "connection_context": None,
        "preflight": ImpactPreflight(
            status="passed",
            analysis_stage_reached="complete",
            checks=(),
            limitations=(),
        ),
        "snapshot": None,
        "summary": ImpactSummary(
            overall_risk=Risk.WARNING,
            critical_count=0,
            warning_count=1,
            safe_count=0,
            not_applicable_count=0,
            would_fail_count=0,
            may_fail_count=0,
            unsupported_count=0,
            no_op_count=0,
            analyzed_count=1,
            incomplete=False,
        ),
        "statements": (one_analyzed_card,),
        "evidence": (one_evidence,),
        "error": None,
    }
