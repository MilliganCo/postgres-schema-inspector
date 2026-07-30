from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from pginspect.impact.models.enums import (
    AnalysisStatus,
    ExecutionPrediction,
    NoOpReason,
    Outcome,
    Risk,
)
from pginspect.impact.models.evidence import ImpactEvidence
from pginspect.impact.models.result import (
    ImpactCommandResult,
    ImpactInputMeta,
    ImpactPreflight,
    ImpactSummary,
)


def test_no_op_requires_reason(minimal_completed_kwargs, one_analyzed_card):
    card = one_analyzed_card.model_copy(
        update={
            "execution_prediction": ExecutionPrediction.NO_OP,
            "no_op_reason": None,
            "risk": Risk.SAFE,
        }
    )
    kwargs = {**minimal_completed_kwargs, "statements": (card,)}
    with pytest.raises(ValidationError):
        ImpactCommandResult(**kwargs)


def test_unsupported_forces_not_evaluated(
    minimal_completed_kwargs, one_analyzed_card, one_evidence
):
    card = one_analyzed_card.model_copy(
        update={
            "analysis_status": AnalysisStatus.UNSUPPORTED_PARSER,
            "execution_prediction": ExecutionPrediction.APPLIES,  # illegal
            "risk": Risk.WARNING,
            "evidence_refs": (one_evidence.evidence_id,),
        }
    )
    kwargs = {
        **minimal_completed_kwargs,
        "statements": (card,),
        "outcome": Outcome.INCOMPLETE,
        "exit_code": 3,
    }
    with pytest.raises(ValidationError):
        ImpactCommandResult(**kwargs)


def test_error_field_is_foundation_execution_error(minimal_completed_kwargs):
    from pginspect.models.enums import ExecutionErrorCategory, ExecutionErrorCode
    from pginspect.models.execution_error import ExecutionError

    err = ExecutionError(
        code=ExecutionErrorCode.INTERNAL_FAILURE,
        category=ExecutionErrorCategory.INTERNAL,
        message="boom",
        retryable=False,
    )
    kwargs = {
        **minimal_completed_kwargs,
        "outcome": Outcome.FAILED,
        "exit_code": 5,
        "statements": (),
        "evidence": (),
        "summary": ImpactSummary(
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
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=0,
            card_count=0,
            control_statement_count=0,
        ),
        "error": err,
    }
    result = ImpactCommandResult(**kwargs)
    assert type(result.error) is ExecutionError


# --- Plan-mandated (a)/(b)/(c) cases ---------------------------------------


def test_preflight_incomplete_with_empty_statements_validates(minimal_completed_kwargs):
    """(a) preflight-incomplete with source_statement_count=3, card_count=0,
    control_statement_count=0, statements=() must validate."""
    kwargs = {
        **minimal_completed_kwargs,
        "outcome": Outcome.INCOMPLETE,
        "exit_code": 3,
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=3,
            card_count=0,
            control_statement_count=0,
        ),
        "preflight": ImpactPreflight(
            status="incomplete",
            analysis_stage_reached="preflight",
            checks=(),
            limitations=(),
        ),
        "summary": ImpactSummary(
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
        "statements": (),
        "evidence": (),
    }
    result = ImpactCommandResult(**kwargs)
    assert result.statements == ()
    assert result.outcome is Outcome.INCOMPLETE


def test_classification_complete_rejects_mismatched_counts(minimal_completed_kwargs):
    """(b) classification-complete completed result with mismatched counts must reject."""
    kwargs = {
        **minimal_completed_kwargs,
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=5,
            card_count=1,
            control_statement_count=0,
        ),
    }
    with pytest.raises(ValidationError, match="classification is complete"):
        ImpactCommandResult(**kwargs)


def test_failed_before_cards_skips_classification_complete_equality(minimal_completed_kwargs):
    """(c) outcome=failed before card assembly with nonzero source_statement_count and
    empty statements must validate without the classification-complete equality."""
    from pginspect.models.enums import ExecutionErrorCategory, ExecutionErrorCode
    from pginspect.models.execution_error import ExecutionError

    kwargs = {
        **minimal_completed_kwargs,
        "outcome": Outcome.FAILED,
        "exit_code": 5,
        "statements": (),
        "evidence": (),
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=7,
            card_count=0,
            control_statement_count=0,
        ),
        "summary": ImpactSummary(
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
        "error": ExecutionError(
            code=ExecutionErrorCode.INTERNAL_FAILURE,
            category=ExecutionErrorCategory.INTERNAL,
            message="boom",
            retryable=False,
        ),
    }
    result = ImpactCommandResult(**kwargs)
    assert result.outcome is Outcome.FAILED
    assert result.statements == ()


# --- Remaining mandatory validator rows -------------------------------------


def test_execution_prediction_not_no_op_forbids_reason(minimal_completed_kwargs, one_analyzed_card):
    card = one_analyzed_card.model_copy(
        update={"no_op_reason": NoOpReason.TARGET_MISSING_IF_EXISTS}
    )
    kwargs = {**minimal_completed_kwargs, "statements": (card,)}
    with pytest.raises(ValidationError, match="no_op_reason must be null"):
        ImpactCommandResult(**kwargs)


def test_card_count_must_equal_len_statements(minimal_completed_kwargs):
    kwargs = {
        **minimal_completed_kwargs,
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=1,
            card_count=0,
            control_statement_count=0,
        ),
    }
    with pytest.raises(ValidationError, match="card_count must equal len"):
        ImpactCommandResult(**kwargs)


def test_source_statement_count_must_be_at_least_control_statement_count(minimal_completed_kwargs):
    kwargs = {
        **minimal_completed_kwargs,
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=1,
            card_count=1,
            control_statement_count=2,
        ),
    }
    with pytest.raises(ValidationError, match="control_statement_count"):
        ImpactCommandResult(**kwargs)


def test_statement_index_must_be_unique(minimal_completed_kwargs, one_analyzed_card):
    duplicate = one_analyzed_card.model_copy(update={"start_line": 2, "end_line": 2})
    kwargs = {
        **minimal_completed_kwargs,
        "statements": (one_analyzed_card, duplicate),
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=2,
            card_count=2,
            control_statement_count=0,
        ),
        "summary": ImpactSummary(
            overall_risk=Risk.WARNING,
            critical_count=0,
            warning_count=2,
            safe_count=0,
            not_applicable_count=0,
            would_fail_count=0,
            may_fail_count=0,
            unsupported_count=0,
            no_op_count=0,
            analyzed_count=2,
            incomplete=False,
        ),
        "evidence": (
            ImpactEvidence(
                evidence_id="rule:add.nullable.no_default",
                kind="semantic_rule",
                summary="nullable add without default",
                attributes={},
            ),
        ),
    }
    with pytest.raises(ValidationError, match="unique"):
        ImpactCommandResult(**kwargs)


def test_statement_index_must_be_ascending(
    minimal_completed_kwargs, one_analyzed_card, one_evidence
):
    second = one_analyzed_card.model_copy(
        update={"statement_index": 1, "start_line": 2, "end_line": 2}
    )
    first = one_analyzed_card.model_copy(update={"statement_index": 2})
    kwargs = {
        **minimal_completed_kwargs,
        "statements": (first, second),
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=2,
            card_count=2,
            control_statement_count=0,
        ),
        "summary": ImpactSummary(
            overall_risk=Risk.WARNING,
            critical_count=0,
            warning_count=2,
            safe_count=0,
            not_applicable_count=0,
            would_fail_count=0,
            may_fail_count=0,
            unsupported_count=0,
            no_op_count=0,
            analyzed_count=2,
            incomplete=False,
        ),
    }
    with pytest.raises(ValidationError, match="ascending"):
        ImpactCommandResult(**kwargs)


def test_evidence_ref_must_exist_in_evidence(minimal_completed_kwargs, one_analyzed_card):
    card = one_analyzed_card.model_copy(update={"evidence_refs": ("missing:ref",)})
    kwargs = {**minimal_completed_kwargs, "statements": (card,)}
    with pytest.raises(ValidationError, match="not found in evidence"):
        ImpactCommandResult(**kwargs)


def test_every_evidence_entry_must_be_referenced(minimal_completed_kwargs, one_evidence):
    unused = ImpactEvidence(
        evidence_id="rule:unused",
        kind="semantic_rule",
        summary="unused evidence",
        attributes={},
    )
    kwargs = {**minimal_completed_kwargs, "evidence": (one_evidence, unused)}
    with pytest.raises(ValidationError, match="referenced by at least one card"):
        ImpactCommandResult(**kwargs)


def test_duration_ms_must_be_non_negative(minimal_completed_kwargs):
    kwargs = {**minimal_completed_kwargs, "duration_ms": -1}
    with pytest.raises(ValidationError):
        ImpactCommandResult(**kwargs)


def test_started_at_must_be_timezone_aware(minimal_completed_kwargs):
    kwargs = {**minimal_completed_kwargs, "started_at": datetime(2026, 7, 29, 12, 0, 0)}
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        ImpactCommandResult(**kwargs)


def test_statement_fingerprint_must_match_pattern(minimal_completed_kwargs, one_analyzed_card):
    card = one_analyzed_card.model_copy(update={"statement_fingerprint": "sha256:short"})
    kwargs = {**minimal_completed_kwargs, "statements": (card,)}
    with pytest.raises(ValidationError, match="sha256"):
        ImpactCommandResult(**kwargs)


def test_sanitized_preview_max_codepoints(minimal_completed_kwargs, one_analyzed_card):
    card = one_analyzed_card.model_copy(update={"sanitized_preview": "x" * 241})
    kwargs = {**minimal_completed_kwargs, "statements": (card,)}
    with pytest.raises(ValidationError, match="240 Unicode code points"):
        ImpactCommandResult(**kwargs)


def test_sanitized_preview_at_exactly_240_codepoints_is_allowed(
    minimal_completed_kwargs, one_analyzed_card
):
    card = one_analyzed_card.model_copy(update={"sanitized_preview": "x" * 240})
    kwargs = {**minimal_completed_kwargs, "statements": (card,)}
    result = ImpactCommandResult(**kwargs)
    assert len(result.statements[0].sanitized_preview) == 240


def test_completed_forbids_unsupported_cards(
    minimal_completed_kwargs, one_analyzed_card, one_evidence
):
    card = one_analyzed_card.model_copy(
        update={
            "analysis_status": AnalysisStatus.UNSUPPORTED_PARSER,
            "execution_prediction": ExecutionPrediction.NOT_EVALUATED,
            "risk": Risk.NOT_APPLICABLE,
        }
    )
    kwargs = {**minimal_completed_kwargs, "statements": (card,)}
    with pytest.raises(ValidationError, match="unsupported_"):
        ImpactCommandResult(**kwargs)


def test_completed_rejects_exit_code_outside_012(minimal_completed_kwargs):
    kwargs = {**minimal_completed_kwargs, "exit_code": 3}
    with pytest.raises(ValidationError):
        ImpactCommandResult(**kwargs)


def test_completed_rejects_non_null_error(minimal_completed_kwargs):
    from pginspect.models.enums import ExecutionErrorCategory, ExecutionErrorCode
    from pginspect.models.execution_error import ExecutionError

    kwargs = {
        **minimal_completed_kwargs,
        "error": ExecutionError(
            code=ExecutionErrorCode.INTERNAL_FAILURE,
            category=ExecutionErrorCategory.INTERNAL,
            message="boom",
            retryable=False,
        ),
    }
    with pytest.raises(ValidationError, match="error=null"):
        ImpactCommandResult(**kwargs)


def test_incomplete_requires_exit_code_3(minimal_completed_kwargs):
    kwargs = {
        **minimal_completed_kwargs,
        "outcome": Outcome.INCOMPLETE,
        "exit_code": 2,
        "summary": minimal_completed_kwargs["summary"].model_copy(update={"incomplete": True}),
    }
    with pytest.raises(ValidationError, match="exit_code=3"):
        ImpactCommandResult(**kwargs)


def test_failed_requires_empty_statements(minimal_completed_kwargs, one_analyzed_card):
    from pginspect.models.enums import ExecutionErrorCategory, ExecutionErrorCode
    from pginspect.models.execution_error import ExecutionError

    kwargs = {
        **minimal_completed_kwargs,
        "outcome": Outcome.FAILED,
        "exit_code": 5,
        "error": ExecutionError(
            code=ExecutionErrorCode.INTERNAL_FAILURE,
            category=ExecutionErrorCategory.INTERNAL,
            message="boom",
            retryable=False,
        ),
        "summary": minimal_completed_kwargs["summary"].model_copy(
            update={"overall_risk": Risk.NOT_APPLICABLE, "incomplete": True}
        ),
    }
    with pytest.raises(ValidationError, match="statements=\\(\\)"):
        ImpactCommandResult(**kwargs)


def test_risk_counts_must_sum_to_len_statements(minimal_completed_kwargs):
    kwargs = {
        **minimal_completed_kwargs,
        "summary": minimal_completed_kwargs["summary"].model_copy(
            update={"warning_count": 0, "safe_count": 0}
        ),
    }
    with pytest.raises(ValidationError, match="must equal len\\(statements\\)"):
        ImpactCommandResult(**kwargs)


def test_overall_risk_must_equal_max_observed_card_risk(minimal_completed_kwargs):
    kwargs = {
        **minimal_completed_kwargs,
        "summary": minimal_completed_kwargs["summary"].model_copy(
            update={"overall_risk": Risk.SAFE, "warning_count": 0, "safe_count": 1}
        ),
    }
    with pytest.raises(ValidationError, match="max observed card risk"):
        ImpactCommandResult(**kwargs)
