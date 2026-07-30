from __future__ import annotations

import dataclasses

import pytest

from pginspect.impact.models.card import ImpactConfidence
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ConfidenceLevel,
    ExecutionPrediction,
    ImpactScaleConfidence,
    LockMode,
    NoOpReason,
    PhysicalTriState,
    Risk,
)
from pginspect.impact.rules import (
    RuleVerdict,
    aggregate_exit_code,
    apply_physical_invariants,
)
from pginspect.impact.rules.contracts import AUTHORIZATION_LIMITATION, StatementExitRow
from pginspect.impact.rules.severity import derive_risk

YES = PhysicalTriState.YES
NO = PhysicalTriState.NO
POSSIBLE = PhysicalTriState.POSSIBLE
UNKNOWN = PhysicalTriState.UNKNOWN
NOT_APPLICABLE = PhysicalTriState.NOT_APPLICABLE

AEL = LockMode.ACCESS_EXCLUSIVE_LOCK
SUEL = LockMode.SHARE_UPDATE_EXCLUSIVE_LOCK


def _confidence() -> ImpactConfidence:
    return ImpactConfidence(
        lock=ConfidenceLevel.HIGH,
        rewrite=ConfidenceLevel.HIGH,
        execution=ConfidenceLevel.HIGH,
        dependencies=ConfidenceLevel.HIGH,
        impact_scale=ImpactScaleConfidence.MEDIUM,
    )


def _risk(
    *,
    execution_prediction: ExecutionPrediction = ExecutionPrediction.APPLIES,
    lock: LockMode = AEL,
    table_rewrite: PhysicalTriState = NO,
    table_scan: PhysicalTriState = NO,
    index_rebuild: PhysicalTriState = NO,
    analysis_status: AnalysisStatus = AnalysisStatus.ANALYZED,
    no_op_reason: NoOpReason | None = None,
    cascade_dependents: bool = False,
) -> Risk:
    return derive_risk(
        execution_prediction=execution_prediction,
        lock=lock,
        table_rewrite=table_rewrite,
        table_scan=table_scan,
        index_rebuild=index_rebuild,
        analysis_status=analysis_status,
        no_op_reason=no_op_reason,
        cascade_dependents=cascade_dependents,
    )


def _row(
    *,
    analysis_status: AnalysisStatus = AnalysisStatus.ANALYZED,
    execution_prediction: ExecutionPrediction = ExecutionPrediction.APPLIES,
    risk: Risk = Risk.SAFE,
) -> StatementExitRow:
    return StatementExitRow(
        analysis_status=analysis_status,
        execution_prediction=execution_prediction,
        risk=risk,
    )


def _verdict(*, risk: Risk = Risk.SAFE) -> RuleVerdict:
    return RuleVerdict(
        rule_key="add.nullable.no_default",
        analysis_status=AnalysisStatus.ANALYZED,
        execution_prediction=ExecutionPrediction.APPLIES,
        risk=risk,
        lock=AEL,
        table_rewrite=NO,
        table_scan=NO,
        index_rebuild=NO,
        confidence=_confidence(),
        limitations=(AUTHORIZATION_LIMITATION,),
        evidence_ids=("rule:add.nullable.no_default",),
    )


@pytest.mark.parametrize("scan", [NO, POSSIBLE, UNKNOWN, NOT_APPLICABLE])
def test_rewrite_yes_forces_scan_yes(scan: PhysicalTriState) -> None:
    assert apply_physical_invariants(YES, scan, NO) == (YES, YES, NO)


def test_rewrite_yes_with_scan_already_yes_is_unchanged() -> None:
    assert apply_physical_invariants(YES, YES, YES) == (YES, YES, YES)


@pytest.mark.parametrize("rewrite", [NO, POSSIBLE, UNKNOWN, NOT_APPLICABLE])
@pytest.mark.parametrize("scan", [NO, POSSIBLE, UNKNOWN, NOT_APPLICABLE])
def test_rewrite_not_yes_does_not_force_scan(
    rewrite: PhysicalTriState, scan: PhysicalTriState
) -> None:
    assert apply_physical_invariants(rewrite, scan, NO) == (rewrite, scan, NO)


@pytest.mark.parametrize("index_rebuild", [YES, NO, POSSIBLE, UNKNOWN, NOT_APPLICABLE])
def test_index_rebuild_is_never_flipped(index_rebuild: PhysicalTriState) -> None:
    assert apply_physical_invariants(YES, NO, index_rebuild)[2] is index_rebuild
    assert apply_physical_invariants(NO, NO, index_rebuild)[2] is index_rebuild


def test_would_fail_is_critical() -> None:
    assert _risk(execution_prediction=ExecutionPrediction.WOULD_FAIL, lock=SUEL) is Risk.CRITICAL


@pytest.mark.parametrize("rewrite", [YES, POSSIBLE])
def test_confirmed_or_possible_rewrite_is_critical(rewrite: PhysicalTriState) -> None:
    assert _risk(table_rewrite=rewrite, table_scan=YES) is Risk.CRITICAL


@pytest.mark.parametrize("index_rebuild", [YES, POSSIBLE])
def test_confirmed_or_possible_index_rebuild_is_critical(index_rebuild: PhysicalTriState) -> None:
    assert _risk(index_rebuild=index_rebuild) is Risk.CRITICAL


@pytest.mark.parametrize("scan", [YES, POSSIBLE])
def test_scan_under_access_exclusive_lock_is_critical(scan: PhysicalTriState) -> None:
    assert _risk(table_scan=scan, lock=AEL) is Risk.CRITICAL


@pytest.mark.parametrize("scan", [YES, POSSIBLE])
def test_scan_under_weaker_lock_is_not_critical(scan: PhysicalTriState) -> None:
    assert _risk(table_scan=scan, lock=SUEL) is Risk.SAFE


def test_may_fail_is_critical() -> None:
    assert _risk(execution_prediction=ExecutionPrediction.MAY_FAIL, lock=SUEL) is Risk.CRITICAL


def test_cascade_with_dependents_is_critical() -> None:
    assert _risk(cascade_dependents=True, lock=SUEL) is Risk.CRITICAL


def test_access_exclusive_lock_without_physical_work_is_warning() -> None:
    assert _risk(lock=AEL, table_rewrite=NO, table_scan=NO, index_rebuild=NO) is Risk.WARNING


def test_deterministic_target_missing_if_exists_is_safe() -> None:
    assert (
        _risk(
            execution_prediction=ExecutionPrediction.NO_OP,
            lock=LockMode.NOT_APPLICABLE,
            table_rewrite=NOT_APPLICABLE,
            table_scan=NOT_APPLICABLE,
            index_rebuild=NOT_APPLICABLE,
            no_op_reason=NoOpReason.TARGET_MISSING_IF_EXISTS,
        )
        is Risk.SAFE
    )


@pytest.mark.parametrize(
    "analysis_status",
    [
        AnalysisStatus.UNSUPPORTED_PARSER,
        AnalysisStatus.UNSUPPORTED_RESOLUTION,
        AnalysisStatus.UNSUPPORTED_SCOPE,
        AnalysisStatus.UNSUPPORTED_EVIDENCE,
        AnalysisStatus.UNSUPPORTED_SEQUENCE,
    ],
)
def test_unavailable_evidence_is_not_applicable(analysis_status: AnalysisStatus) -> None:
    assert (
        _risk(
            analysis_status=analysis_status,
            execution_prediction=ExecutionPrediction.NOT_EVALUATED,
            table_rewrite=YES,
        )
        is Risk.NOT_APPLICABLE
    )


def test_metadata_only_change_under_weak_lock_is_safe() -> None:
    assert _risk(lock=SUEL) is Risk.SAFE


def test_exit_code_zero_when_everything_is_analyzed_and_safe() -> None:
    assert aggregate_exit_code(statements=(_row(), _row(risk=Risk.NOT_APPLICABLE))) == 0


def test_exit_code_zero_for_no_statements() -> None:
    assert aggregate_exit_code(statements=()) == 0


def test_exit_code_one_for_warning() -> None:
    assert aggregate_exit_code(statements=(_row(), _row(risk=Risk.WARNING))) == 1


def test_exit_code_two_for_critical() -> None:
    assert aggregate_exit_code(statements=(_row(risk=Risk.WARNING), _row(risk=Risk.CRITICAL))) == 2


def test_exit_code_two_for_would_fail_even_without_critical_risk() -> None:
    assert (
        aggregate_exit_code(statements=(_row(execution_prediction=ExecutionPrediction.WOULD_FAIL),))
        == 2
    )


@pytest.mark.parametrize(
    "analysis_status",
    [
        AnalysisStatus.UNSUPPORTED_PARSER,
        AnalysisStatus.UNSUPPORTED_RESOLUTION,
        AnalysisStatus.UNSUPPORTED_SCOPE,
        AnalysisStatus.UNSUPPORTED_EVIDENCE,
        AnalysisStatus.UNSUPPORTED_SEQUENCE,
    ],
)
def test_exit_code_three_for_any_unsupported_statement(analysis_status: AnalysisStatus) -> None:
    statements = (
        _row(risk=Risk.CRITICAL, execution_prediction=ExecutionPrediction.WOULD_FAIL),
        _row(
            analysis_status=analysis_status,
            execution_prediction=ExecutionPrediction.NOT_EVALUATED,
            risk=Risk.NOT_APPLICABLE,
        ),
    )
    assert aggregate_exit_code(statements=statements) == 3


def test_exit_code_three_for_incomplete_preflight_with_no_statements() -> None:
    assert aggregate_exit_code(preflight_incomplete=True, statements=()) == 3


def test_rule_verdict_is_usable_as_an_exit_view() -> None:
    assert aggregate_exit_code(statements=(_verdict(risk=Risk.WARNING),)) == 1


def test_rule_verdict_is_frozen() -> None:
    verdict = _verdict()
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.risk = Risk.CRITICAL  # type: ignore[misc]


def test_rule_verdict_optional_fields_default_to_empty() -> None:
    verdict = _verdict()
    assert verdict.no_op_reason is None
    assert verdict.why == ()


def test_authorization_limitation_is_the_exact_design_text() -> None:
    assert AUTHORIZATION_LIMITATION == (
        "Authorization failures are not modeled; analysis assumes sufficient privileges."
    )


def test_rules_package_exports_task_5_and_task_6_surface() -> None:
    import pginspect.impact.rules as rules

    assert set(rules.__all__) == {
        "CoercionLookupResult",
        "RuleVerdict",
        "aggregate_exit_code",
        "apply_physical_invariants",
        "lookup_coercion",
    }
