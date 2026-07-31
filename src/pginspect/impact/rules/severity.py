"""Deterministic severity, physical invariants, and exit aggregation.

Design sections 3.3 (severity) and 3.9 (exit aggregation). Every rule engine
routes its physical flags through `apply_physical_invariants` and its risk
through `derive_risk` so two engines can never disagree about the same
combination of facts.
"""

from __future__ import annotations

from collections.abc import Sequence

from pginspect.impact.models.enums import (
    AnalysisStatus,
    ExecutionPrediction,
    LockMode,
    NoOpReason,
    PhysicalTriState,
    Risk,
)
from pginspect.impact.rules.contracts import StatementExitView

__all__ = ["aggregate_exit_code", "apply_physical_invariants", "derive_risk"]

_CONFIRMED_OR_POSSIBLE = frozenset({PhysicalTriState.YES, PhysicalTriState.POSSIBLE})


def apply_physical_invariants(
    rewrite: PhysicalTriState,
    scan: PhysicalTriState,
    index_rebuild: PhysicalTriState,
) -> tuple[PhysicalTriState, PhysicalTriState, PhysicalTriState]:
    """Return `(rewrite, scan, index_rebuild)` with `rewrite=yes ⇒ scan=yes` enforced.

    A rewrite reads every live row, so a confirmed rewrite always implies a
    confirmed scan. This is the only correction applied: `index_rebuild`
    depends on facts (affected indexes) this helper does not see, so it is
    returned untouched and stays the caller's responsibility.
    """
    if rewrite is PhysicalTriState.YES and scan is not PhysicalTriState.YES:
        return (rewrite, PhysicalTriState.YES, index_rebuild)
    return (rewrite, scan, index_rebuild)


def derive_risk(
    *,
    execution_prediction: ExecutionPrediction,
    lock: LockMode,
    table_rewrite: PhysicalTriState,
    table_scan: PhysicalTriState,
    index_rebuild: PhysicalTriState,
    analysis_status: AnalysisStatus = AnalysisStatus.ANALYZED,
    no_op_reason: NoOpReason | None = None,
    cascade_dependents: bool = False,
) -> Risk:
    """Map one statement's proven facts onto a risk level (design section 3.3).

    `cascade_dependents` is the caller's flag for a CASCADE statement that
    has external or cascade-role dependents. Anything that is not `analyzed`
    reports `not_applicable`: the required evidence was unavailable, so no
    risk claim can be made.

    Deterministic IF EXISTS no-ops (`target_missing_if_exists` and
    `column_missing_if_exists`) are checked before the lock-only warning:
    a proven no-op contributes risk=safe and must not raise the process
    exit above 0 (owner Layer D remediation).
    """
    if analysis_status is not AnalysisStatus.ANALYZED:
        return Risk.NOT_APPLICABLE
    if execution_prediction is ExecutionPrediction.WOULD_FAIL:
        return Risk.CRITICAL
    if table_rewrite in _CONFIRMED_OR_POSSIBLE:
        return Risk.CRITICAL
    if index_rebuild in _CONFIRMED_OR_POSSIBLE:
        return Risk.CRITICAL
    if table_scan in _CONFIRMED_OR_POSSIBLE and lock is LockMode.ACCESS_EXCLUSIVE_LOCK:
        return Risk.CRITICAL
    if execution_prediction is ExecutionPrediction.MAY_FAIL:
        return Risk.CRITICAL
    if cascade_dependents:
        return Risk.CRITICAL
    if no_op_reason in {
        NoOpReason.TARGET_MISSING_IF_EXISTS,
        NoOpReason.COLUMN_MISSING_IF_EXISTS,
    }:
        return Risk.SAFE
    if (
        lock is LockMode.ACCESS_EXCLUSIVE_LOCK
        and table_rewrite is PhysicalTriState.NO
        and table_scan is PhysicalTriState.NO
        and index_rebuild is PhysicalTriState.NO
    ):
        return Risk.WARNING
    return Risk.SAFE


def aggregate_exit_code(
    *,
    preflight_incomplete: bool = False,
    statements: Sequence[StatementExitView],
) -> int:
    """Reduce every statement view to the process exit code (design section 3.9).

    Incompleteness outranks severity: an `unsupported_*` statement or an
    incomplete preflight means the run cannot claim to have seen everything,
    which is reported as 3 rather than a possibly understated 0/1/2.
    """
    if preflight_incomplete:
        return 3
    if any(view.analysis_status is not AnalysisStatus.ANALYZED for view in statements):
        return 3
    if any(view.execution_prediction is ExecutionPrediction.WOULD_FAIL for view in statements):
        return 2
    if any(view.risk is Risk.CRITICAL for view in statements):
        return 2
    if any(view.risk is Risk.WARNING for view in statements):
        return 1
    return 0
