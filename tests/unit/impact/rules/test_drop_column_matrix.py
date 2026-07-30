"""Full DROP COLUMN rule matrix (plan Task 9, design section 3.8).

Covers every mandatory case: no dependents, internal-only (D1), automatic
dependents, external blocker under RESTRICT/default (D2), CASCADE with
external/cascade dependents (D3), a truncated graph, and missing required
evidence. Pure fact-to-verdict tests — no catalog, no psycopg.
"""

from __future__ import annotations

import ast
import dataclasses
from collections.abc import Callable
from pathlib import Path

import pytest

from pginspect.impact.models.catalog_types import DependencyEdge
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ConfidenceLevel,
    ExecutionPrediction,
    ImpactScaleConfidence,
    LockMode,
    PhysicalTriState,
    Risk,
)
from pginspect.impact.rules.contracts import AUTHORIZATION_LIMITATION, RuleVerdict
from pginspect.impact.rules.drop_column import (
    DROP_COLUMN_DEPENDENCY_LIMITATION,
    DROP_COLUMN_INCOMPLETE_EVIDENCE_LIMITATION,
    DROP_COLUMN_METRICS_LIMITATION,
    RULE_KEY_AUTOMATIC_ONLY,
    RULE_KEY_CASCADE_EXTERNAL,
    RULE_KEY_EXTERNAL_BLOCKER_RESTRICT,
    RULE_KEY_INTERNAL_ONLY,
    RULE_KEY_NO_DEPENDENTS,
    RULE_KEY_UNSUPPORTED_EVIDENCE,
    DropColumnFacts,
    evaluate_drop_column,
)
from pginspect.impact.rules.severity import aggregate_exit_code
from .factories_drop import (
    automatic_default_edge,
    cascade_view_edge,
    drop_facts,
    external_view_edge,
    internal_index_edge,
)

NO = PhysicalTriState.NO
AEL = LockMode.ACCESS_EXCLUSIVE_LOCK

_BEHAVIORS: tuple[str, ...] = ("restrict", "cascade")


def _analyzed_cases() -> dict[str, DropColumnFacts]:
    """One representative facts object per analyzed row of the matrix."""
    return {
        "no_dependents": drop_facts(),
        "internal_only": drop_facts(edges=(internal_index_edge(),)),
        "automatic_only": drop_facts(edges=(automatic_default_edge(),)),
        "external_restrict": drop_facts(edges=(external_view_edge(),)),
        "external_cascade": drop_facts(edges=(external_view_edge(),), effective_behavior="cascade"),
        "cascade_bucket": drop_facts(edges=(cascade_view_edge(),), effective_behavior="cascade"),
    }


def _unsupported_cases() -> dict[str, DropColumnFacts]:
    """One representative facts object per way required evidence can be absent."""
    return {
        "truncated": drop_facts(edges=(internal_index_edge(),), truncated_at_limit=True),
        "graph_incomplete": drop_facts(dependency_graph_complete=False),
        "required_missing": drop_facts(required_evidence_missing=True),
        "table_missing": drop_facts(table_exists=False),
        "column_missing": drop_facts(column_exists=False),
    }


def _all_cases() -> dict[str, DropColumnFacts]:
    return {**_analyzed_cases(), **_unsupported_cases()}


def _case_params(cases: Callable[[], dict[str, DropColumnFacts]]) -> list[object]:
    return [pytest.param(facts, id=name) for name, facts in cases().items()]


# --- mandatory case: no dependents -----------------------------------------


def test_no_dependents_applies_as_warning() -> None:
    verdict = evaluate_drop_column(drop_facts())

    assert verdict.rule_key == RULE_KEY_NO_DEPENDENTS
    assert verdict.analysis_status is AnalysisStatus.ANALYZED
    assert verdict.execution_prediction is ExecutionPrediction.APPLIES
    assert verdict.risk is Risk.WARNING
    assert verdict.lock is AEL
    assert verdict.evidence_ids == ("rule:drop.no_dependents",)


# --- mandatory case: internal-only (D1) ------------------------------------


def test_d1_internal_index_dependent_applies_as_warning() -> None:
    verdict = evaluate_drop_column(drop_facts(edges=(internal_index_edge(),)))

    assert verdict.rule_key == RULE_KEY_INTERNAL_ONLY
    assert verdict.analysis_status is AnalysisStatus.ANALYZED
    assert verdict.execution_prediction is ExecutionPrediction.APPLIES
    assert verdict.risk is Risk.WARNING
    assert verdict.evidence_ids == ("rule:drop.internal_only",)


@pytest.mark.parametrize("behavior", _BEHAVIORS)
def test_internal_only_verdict_does_not_depend_on_behavior(behavior: str) -> None:
    facts = drop_facts(edges=(internal_index_edge(),), effective_behavior=behavior)  # type: ignore[arg-type]

    verdict = evaluate_drop_column(facts)

    assert verdict.rule_key == RULE_KEY_INTERNAL_ONLY
    assert verdict.risk is Risk.WARNING


# --- mandatory case: automatic dependents ----------------------------------


def test_automatic_dependents_apply_as_warning() -> None:
    verdict = evaluate_drop_column(drop_facts(edges=(automatic_default_edge(),)))

    assert verdict.rule_key == RULE_KEY_AUTOMATIC_ONLY
    assert verdict.execution_prediction is ExecutionPrediction.APPLIES
    assert verdict.risk is Risk.WARNING
    assert verdict.evidence_ids == ("rule:drop.automatic_only",)


def test_mixed_internal_and_automatic_reports_the_internal_key() -> None:
    facts = drop_facts(edges=(automatic_default_edge(), internal_index_edge()))

    verdict = evaluate_drop_column(facts)

    assert verdict.rule_key == RULE_KEY_INTERNAL_ONLY
    assert verdict.risk is Risk.WARNING


# --- mandatory case: external blocker + RESTRICT/default (D2) --------------


def test_d2_external_blocker_under_restrict_would_fail() -> None:
    verdict = evaluate_drop_column(drop_facts(edges=(external_view_edge(),)))

    assert verdict.rule_key == RULE_KEY_EXTERNAL_BLOCKER_RESTRICT
    assert verdict.analysis_status is AnalysisStatus.ANALYZED
    assert verdict.execution_prediction is ExecutionPrediction.WOULD_FAIL
    assert verdict.risk is Risk.CRITICAL
    assert verdict.evidence_ids == ("rule:drop.external_blocker_restrict",)


def test_written_restrict_and_omitted_behavior_are_the_same_verdict() -> None:
    """The parser resolves a default behavior to `restrict` (design section 1b)."""
    edges = (external_view_edge(),)

    written = evaluate_drop_column(drop_facts(edges=edges, effective_behavior="restrict"))
    defaulted = evaluate_drop_column(drop_facts(edges=edges))

    assert written == defaulted


def test_external_blocker_count_is_reported_in_why() -> None:
    edges = (external_view_edge(objid=16_601), external_view_edge(objid=16_602))

    verdict = evaluate_drop_column(drop_facts(edges=edges))

    assert verdict.why == (
        "2 catalog-proven external dependent object(s) block the drop under "
        "RESTRICT (written or default) behavior.",
    )


def test_internal_dependents_never_turn_a_drop_into_would_fail() -> None:
    facts = drop_facts(edges=(internal_index_edge(), automatic_default_edge()))

    assert evaluate_drop_column(facts).execution_prediction is ExecutionPrediction.APPLIES


# --- mandatory case: CASCADE + external/cascade (D3) -----------------------


def test_d3_external_dependent_under_cascade_applies_as_critical() -> None:
    facts = drop_facts(edges=(external_view_edge(),), effective_behavior="cascade")

    verdict = evaluate_drop_column(facts)

    assert verdict.rule_key == RULE_KEY_CASCADE_EXTERNAL
    assert verdict.analysis_status is AnalysisStatus.ANALYZED
    assert verdict.execution_prediction is ExecutionPrediction.APPLIES
    assert verdict.risk is Risk.CRITICAL
    assert verdict.evidence_ids == ("rule:drop.cascade_external",)


@pytest.mark.parametrize("behavior", _BEHAVIORS)
def test_cascade_bucketed_dependent_is_always_a_cascade_drop(behavior: str) -> None:
    """Bucketing is the catalog layer's call: a blocker is bucketed `external_blocking`."""
    facts = drop_facts(edges=(cascade_view_edge(),), effective_behavior=behavior)  # type: ignore[arg-type]

    verdict = evaluate_drop_column(facts)

    assert verdict.rule_key == RULE_KEY_CASCADE_EXTERNAL
    assert verdict.execution_prediction is ExecutionPrediction.APPLIES
    assert verdict.risk is Risk.CRITICAL


def test_cascade_critical_survives_no_physical_work() -> None:
    """`critical` here comes from cascade dependents, not from rewrite/scan/index work."""
    facts = drop_facts(edges=(external_view_edge(),), effective_behavior="cascade")

    verdict = evaluate_drop_column(facts)

    assert (verdict.table_rewrite, verdict.table_scan, verdict.index_rebuild) == (NO, NO, NO)
    assert verdict.risk is Risk.CRITICAL


def test_cascade_counts_external_and_cascade_dependents() -> None:
    edges = (external_view_edge(), cascade_view_edge(), internal_index_edge())

    verdict = evaluate_drop_column(drop_facts(edges=edges, effective_behavior="cascade"))

    assert verdict.why == (
        "CASCADE drops 2 catalog-proven dependent object(s) beyond the target column.",
    )


def test_external_blocker_outranks_cascade_bucket_under_restrict() -> None:
    edges = (cascade_view_edge(), external_view_edge())

    verdict = evaluate_drop_column(drop_facts(edges=edges))

    assert verdict.rule_key == RULE_KEY_EXTERNAL_BLOCKER_RESTRICT
    assert verdict.execution_prediction is ExecutionPrediction.WOULD_FAIL


# --- mandatory case: truncated / missing evidence --------------------------


@pytest.mark.parametrize("facts", _case_params(_unsupported_cases))
def test_incomplete_evidence_is_unsupported_and_not_evaluated(facts: DropColumnFacts) -> None:
    verdict = evaluate_drop_column(facts)

    assert verdict.rule_key == RULE_KEY_UNSUPPORTED_EVIDENCE
    assert verdict.analysis_status is AnalysisStatus.UNSUPPORTED_EVIDENCE
    assert verdict.execution_prediction is ExecutionPrediction.NOT_EVALUATED
    assert verdict.risk is Risk.NOT_APPLICABLE
    assert verdict.evidence_ids == ("rule:drop.unsupported_evidence",)


@pytest.mark.parametrize("facts", _case_params(_unsupported_cases))
def test_incomplete_evidence_never_claims_applies_or_would_fail(facts: DropColumnFacts) -> None:
    verdict = evaluate_drop_column(facts)

    assert verdict.execution_prediction not in (
        ExecutionPrediction.APPLIES,
        ExecutionPrediction.WOULD_FAIL,
        ExecutionPrediction.NO_OP,
    )
    assert verdict.risk not in (Risk.SAFE, Risk.WARNING, Risk.CRITICAL)


def test_truncation_outranks_an_otherwise_harmless_dependency_set() -> None:
    """An internal-only graph is still unjudgeable once the BFS was cut short."""
    facts = drop_facts(edges=(internal_index_edge(),), truncated_at_limit=True)

    assert evaluate_drop_column(facts).analysis_status is AnalysisStatus.UNSUPPORTED_EVIDENCE


def test_truncation_outranks_a_proven_external_blocker() -> None:
    facts = drop_facts(edges=(external_view_edge(),), truncated_at_limit=True)

    assert evaluate_drop_column(facts).analysis_status is AnalysisStatus.UNSUPPORTED_EVIDENCE


@pytest.mark.parametrize("facts", _case_params(_unsupported_cases))
def test_incomplete_evidence_aggregates_to_exit_three(facts: DropColumnFacts) -> None:
    assert aggregate_exit_code(statements=(evaluate_drop_column(facts),)) == 3


def test_unresolved_target_makes_no_lock_claim() -> None:
    verdict = evaluate_drop_column(drop_facts(column_exists=False))

    assert verdict.lock is LockMode.UNKNOWN
    assert verdict.confidence.lock is ConfidenceLevel.NOT_APPLICABLE


def test_resolved_target_keeps_the_lock_claim_when_the_graph_is_truncated() -> None:
    verdict = evaluate_drop_column(drop_facts(truncated_at_limit=True))

    assert verdict.lock is AEL
    assert verdict.confidence.lock is ConfidenceLevel.HIGH


@pytest.mark.parametrize("facts", _case_params(_unsupported_cases))
def test_incomplete_evidence_explains_itself(facts: DropColumnFacts) -> None:
    verdict = evaluate_drop_column(facts)

    assert len(verdict.why) == 1
    assert verdict.why[0].startswith("Analysis skipped: ")


# --- physical invariants ---------------------------------------------------


@pytest.mark.parametrize("facts", _case_params(_all_cases))
def test_physical_axes_are_always_no(facts: DropColumnFacts) -> None:
    verdict = evaluate_drop_column(facts)

    assert verdict.table_rewrite is NO
    assert verdict.table_scan is NO
    assert verdict.index_rebuild is NO


@pytest.mark.parametrize("facts", _case_params(_analyzed_cases))
def test_analyzed_verdicts_lock_access_exclusive(facts: DropColumnFacts) -> None:
    assert evaluate_drop_column(facts).lock is AEL


# --- limitations and confidence --------------------------------------------


@pytest.mark.parametrize("facts", _case_params(_analyzed_cases))
def test_analyzed_verdicts_carry_the_authorization_limitation(facts: DropColumnFacts) -> None:
    assert AUTHORIZATION_LIMITATION in evaluate_drop_column(facts).limitations


@pytest.mark.parametrize("facts", _case_params(_analyzed_cases))
def test_analyzed_verdicts_disclose_catalog_only_dependency_proof(
    facts: DropColumnFacts,
) -> None:
    assert DROP_COLUMN_DEPENDENCY_LIMITATION in evaluate_drop_column(facts).limitations


def test_dependency_limitation_names_textual_and_dynamic_references() -> None:
    assert "textual" in DROP_COLUMN_DEPENDENCY_LIMITATION
    assert "dynamic" in DROP_COLUMN_DEPENDENCY_LIMITATION


@pytest.mark.parametrize("facts", _case_params(_unsupported_cases))
def test_unsupported_verdicts_do_not_qualify_an_analysis_that_never_ran(
    facts: DropColumnFacts,
) -> None:
    limitations = evaluate_drop_column(facts).limitations

    assert limitations == (DROP_COLUMN_INCOMPLETE_EVIDENCE_LIMITATION,)


def test_missing_metrics_lower_impact_scale_without_changing_the_verdict() -> None:
    edges = (internal_index_edge(),)

    with_metrics = evaluate_drop_column(drop_facts(edges=edges, metrics_present=True))
    without_metrics = evaluate_drop_column(drop_facts(edges=edges, metrics_present=False))

    assert with_metrics.confidence.impact_scale is ImpactScaleConfidence.MEDIUM
    assert without_metrics.confidence.impact_scale is ImpactScaleConfidence.UNKNOWN
    assert DROP_COLUMN_METRICS_LIMITATION not in with_metrics.limitations
    assert DROP_COLUMN_METRICS_LIMITATION in without_metrics.limitations
    assert _semantics(with_metrics) == _semantics(without_metrics)


@pytest.mark.parametrize("facts", _case_params(_analyzed_cases))
def test_analyzed_verdicts_claim_dependency_confidence(facts: DropColumnFacts) -> None:
    assert evaluate_drop_column(facts).confidence.dependencies is ConfidenceLevel.HIGH


@pytest.mark.parametrize("facts", _case_params(_unsupported_cases))
def test_unsupported_verdicts_claim_no_dependency_confidence(facts: DropColumnFacts) -> None:
    confidence = evaluate_drop_column(facts).confidence

    assert confidence.dependencies is ConfidenceLevel.NOT_APPLICABLE
    assert confidence.execution is ConfidenceLevel.NOT_APPLICABLE
    assert confidence.impact_scale is ImpactScaleConfidence.NOT_APPLICABLE


# --- shape and boundary ----------------------------------------------------


@pytest.mark.parametrize("facts", _case_params(_all_cases))
def test_rule_key_and_evidence_id_agree(facts: DropColumnFacts) -> None:
    verdict = evaluate_drop_column(facts)

    assert verdict.evidence_ids == (f"rule:{verdict.rule_key}",)
    assert verdict.rule_key.startswith("drop.")


@pytest.mark.parametrize("facts", _case_params(_all_cases))
def test_no_op_is_never_reported_by_this_rule(facts: DropColumnFacts) -> None:
    """`IF EXISTS` no-ops are decided before scoring; the rule makes no such claim."""
    assert evaluate_drop_column(facts).no_op_reason is None


@pytest.mark.parametrize("facts", _case_params(_all_cases))
def test_evaluation_is_deterministic(facts: DropColumnFacts) -> None:
    assert evaluate_drop_column(facts) == evaluate_drop_column(facts)


def test_facts_are_frozen() -> None:
    facts = drop_facts()

    with pytest.raises(dataclasses.FrozenInstanceError):
        facts.column_exists = False  # type: ignore[misc]


def test_edge_order_does_not_change_the_verdict() -> None:
    edges: tuple[DependencyEdge, ...] = (
        internal_index_edge(),
        external_view_edge(),
        automatic_default_edge(),
    )

    forward = evaluate_drop_column(drop_facts(edges=edges))
    reversed_ = evaluate_drop_column(drop_facts(edges=tuple(reversed(edges))))

    assert forward == reversed_


def test_module_imports_no_database_driver() -> None:
    source = (
        Path(__file__).resolve().parents[4]
        / "src"
        / "pginspect"
        / "impact"
        / "rules"
        / "drop_column.py"
    )
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])

    assert "psycopg" not in imported


def _semantics(verdict: RuleVerdict) -> tuple[object, ...]:
    return (
        verdict.rule_key,
        verdict.analysis_status,
        verdict.execution_prediction,
        verdict.risk,
        verdict.lock,
        verdict.table_rewrite,
        verdict.table_scan,
        verdict.index_rebuild,
        verdict.evidence_ids,
    )
