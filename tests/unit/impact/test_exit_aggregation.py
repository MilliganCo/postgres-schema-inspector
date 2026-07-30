"""Exit aggregation coverage used by `run_impact` (design §3.9 / Task 10)."""

from __future__ import annotations

from pginspect.impact.models.card import ImpactConfidence, ImpactStatementCard
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ConfidenceLevel,
    ExecutionPrediction,
    ImpactScaleConfidence,
    LockMode,
    PhysicalTriState,
    Risk,
)
from pginspect.impact.rules.contracts import StatementExitRow
from pginspect.impact.rules.severity import aggregate_exit_code


def _card(
    *,
    index: int,
    status: AnalysisStatus = AnalysisStatus.ANALYZED,
    execution: ExecutionPrediction = ExecutionPrediction.APPLIES,
    risk: Risk = Risk.WARNING,
) -> ImpactStatementCard:
    return ImpactStatementCard(
        statement_index=index,
        start_line=index,
        end_line=index,
        statement_fingerprint=f"sha256:{index:016x}",
        sanitized_preview=f"stmt {index}",
        analysis_status=status,
        execution_prediction=execution,
        no_op_reason=None,
        risk=risk,
        confidence=ImpactConfidence(
            lock=ConfidenceLevel.HIGH,
            rewrite=ConfidenceLevel.HIGH,
            execution=ConfidenceLevel.HIGH,
            dependencies=ConfidenceLevel.HIGH,
            impact_scale=ImpactScaleConfidence.MEDIUM,
        ),
        lock=LockMode.ACCESS_EXCLUSIVE_LOCK,
        table_rewrite=PhysicalTriState.NO,
        table_scan=PhysicalTriState.NO,
        index_rebuild=PhysicalTriState.NO,
        limitations=(),
        evidence_refs=(),
    )


def test_aggregate_exit_all_clear_is_zero() -> None:
    assert (
        aggregate_exit_code(
            statements=(
                StatementExitRow(AnalysisStatus.ANALYZED, ExecutionPrediction.APPLIES, Risk.SAFE),
            )
        )
        == 0
    )


def test_aggregate_exit_warning_is_one() -> None:
    assert aggregate_exit_code(statements=(_card(index=1, risk=Risk.WARNING),)) == 1


def test_aggregate_exit_critical_is_two() -> None:
    assert aggregate_exit_code(statements=(_card(index=1, risk=Risk.CRITICAL),)) == 2


def test_aggregate_exit_would_fail_is_two() -> None:
    assert (
        aggregate_exit_code(
            statements=(
                _card(
                    index=1,
                    execution=ExecutionPrediction.WOULD_FAIL,
                    risk=Risk.CRITICAL,
                ),
            )
        )
        == 2
    )


def test_aggregate_exit_unsupported_is_three() -> None:
    assert (
        aggregate_exit_code(
            statements=(
                _card(
                    index=1,
                    status=AnalysisStatus.UNSUPPORTED_SEQUENCE,
                    execution=ExecutionPrediction.NOT_EVALUATED,
                    risk=Risk.NOT_APPLICABLE,
                ),
            )
        )
        == 3
    )


def test_aggregate_exit_preflight_incomplete_is_three() -> None:
    assert aggregate_exit_code(preflight_incomplete=True, statements=()) == 3


def test_aggregate_exit_priority_incomplete_over_critical() -> None:
    assert (
        aggregate_exit_code(
            statements=(
                _card(index=1, risk=Risk.CRITICAL),
                _card(
                    index=2,
                    status=AnalysisStatus.UNSUPPORTED_EVIDENCE,
                    execution=ExecutionPrediction.NOT_EVALUATED,
                    risk=Risk.NOT_APPLICABLE,
                ),
            )
        )
        == 3
    )
