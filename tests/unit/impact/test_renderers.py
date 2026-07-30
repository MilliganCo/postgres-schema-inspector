"""Renderer tests for ImpactCommandResult (plan Task 11)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pginspect.impact.models.card import ImpactConfidence, ImpactStatementCard
from pginspect.impact.models.enums import (
    AnalysisStage,
    AnalysisStatus,
    ExecutionPrediction,
    LockMode,
    Outcome,
    PhysicalTriState,
    PreflightStatus,
    Risk,
)
from pginspect.impact.models.evidence import ImpactEvidence
from pginspect.impact.models.result import (
    ImpactCommandResult,
    ImpactInputMeta,
    ImpactPreflight,
    ImpactSummary,
)
from pginspect.impact.renderers import (
    render_impact_json,
    render_impact_text,
    render_impact_text_debug,
)
from pginspect.models.enums import ExecutionErrorCategory, ExecutionErrorCode
from pginspect.models.execution_error import DebugPayload, ExecutionError

AUTH = "Authorization failures are not modeled; analysis assumes sufficient privileges."


def _minimal_result(**overrides: object) -> ImpactCommandResult:
    evidence = ImpactEvidence(
        evidence_id="rule:add.nullable.no_default",
        kind="semantic_rule",
        summary="nullable add",
        attributes={"rule_key": "add.nullable.no_default"},
    )
    card = ImpactStatementCard(
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
        why=("metadata-only add",),
        limitations=(AUTH,),
        evidence_refs=(evidence.evidence_id,),
    )
    kwargs: dict[str, object] = {
        "outcome": Outcome.COMPLETED,
        "exit_code": 1,
        "started_at": datetime(2026, 7, 30, 12, 0, 0, tzinfo=UTC),
        "duration_ms": 5,
        "app_version": "0.0.0",
        "input": ImpactInputMeta(
            path_basename="migration.sql",
            source_statement_count=1,
            card_count=1,
            control_statement_count=0,
        ),
        "connection_context": None,
        "preflight": ImpactPreflight(
            status=PreflightStatus.PASSED,
            analysis_stage_reached=AnalysisStage.COMPLETE,
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
        "statements": (card,),
        "evidence": (evidence,),
        "error": None,
    }
    kwargs.update(overrides)
    return ImpactCommandResult(**kwargs)  # type: ignore[arg-type]


def test_json_is_one_object_plus_newline() -> None:
    text = render_impact_json(_minimal_result())
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    payload = json.loads(text)
    assert isinstance(payload, dict)
    assert payload["command"] == "impact"
    assert payload["input"]["path_basename"] == "migration.sql"


def test_json_and_text_omit_full_path_and_raw_sql() -> None:
    result = _minimal_result()
    full_path = r"E:\secrets\migrations\do_not_leak.sql"
    raw_sql = "ALTER TABLE t ADD COLUMN secret text DEFAULT 'raw'"
    json_text = render_impact_json(result)
    text = render_impact_text(result)
    assert full_path not in json_text
    assert full_path not in text
    assert raw_sql not in json_text
    assert raw_sql not in text
    assert "migration.sql" in json_text
    assert "migration.sql" in text


def test_text_debug_only_when_debug_payload_present() -> None:
    assert render_impact_text_debug(_minimal_result()) is None
    failed = _minimal_result(
        outcome=Outcome.FAILED,
        exit_code=5,
        statements=(),
        evidence=(),
        summary=ImpactSummary(
            overall_risk=Risk.NOT_APPLICABLE,
            critical_count=0,
            warning_count=0,
            safe_count=0,
            not_applicable_count=0,
            would_fail_count=0,
            may_fail_count=0,
            unsupported_count=0,
            no_op_count=0,
            analyzed_count=0,
            incomplete=True,
        ),
        input=ImpactInputMeta(
            path_basename="migration.sql",
            source_statement_count=1,
            card_count=0,
            control_statement_count=0,
        ),
        error=ExecutionError(
            code=ExecutionErrorCode.INTERNAL_FAILURE,
            category=ExecutionErrorCategory.INTERNAL,
            message="pginspect failed due to an internal error.",
            retryable=False,
            debug=DebugPayload(exception_type="RuntimeError", causal_chain_types=(), frames=()),
        ),
    )
    debug = render_impact_text_debug(failed)
    assert debug is not None
    assert debug.startswith("Debug:")
    assert debug.endswith("\n")
    assert "RuntimeError" in debug
