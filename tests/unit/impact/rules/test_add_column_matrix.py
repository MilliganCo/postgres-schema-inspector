"""Full ADD COLUMN matrix (plan Task 8, design section 3.7)."""

from __future__ import annotations

import ast
import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import pginspect.impact.rules.add_column as add_column_module
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ConfidenceLevel,
    ExecutionPrediction,
    ImpactScaleConfidence,
    LockMode,
    PhysicalTriState,
    Risk,
)
from pginspect.impact.rules.add_column import (
    TABLE_EMPTINESS_LIMITATION,
    AddColumnFacts,
    evaluate_add_column,
)
from pginspect.impact.rules.contracts import AUTHORIZATION_LIMITATION, RuleVerdict
from . import factories_add as f

YES = PhysicalTriState.YES
NO = PhysicalTriState.NO
POSSIBLE = PhysicalTriState.POSSIBLE
NOT_APPLICABLE = PhysicalTriState.NOT_APPLICABLE

APPLIES = ExecutionPrediction.APPLIES
MAY_FAIL = ExecutionPrediction.MAY_FAIL
WOULD_FAIL = ExecutionPrediction.WOULD_FAIL

MatrixRow = tuple[
    str,
    Callable[[], AddColumnFacts],
    str,
    ExecutionPrediction,
    PhysicalTriState,
    PhysicalTriState,
    PhysicalTriState,
    Risk,
]

MANDATORY_MATRIX: tuple[MatrixRow, ...] = (
    (
        "coercion invalid",
        f.coercion_invalid,
        "add.coercion_invalid",
        WOULD_FAIL,
        NOT_APPLICABLE,
        NOT_APPLICABLE,
        NOT_APPLICABLE,
        Risk.CRITICAL,
    ),
    (
        "A1 nullable, effective_default NULL",
        f.a1_nullable_no_default,
        "add.nullable.no_default",
        APPLIES,
        NO,
        NO,
        NO,
        Risk.WARNING,
    ),
    (
        "A2 nullable, const DEFAULT false",
        f.a2_nullable_const_default,
        "add.nullable.const_or_nonvolatile_valid",
        APPLIES,
        NO,
        NO,
        NO,
        Risk.WARNING,
    ),
    (
        "effective domain default, classifiable nonvolatile",
        f.nullable_domain_default_nonvolatile,
        "add.nullable.const_or_nonvolatile_valid",
        APPLIES,
        NO,
        NO,
        NO,
        Risk.WARNING,
    ),
    (
        "unknown domain default, indexes=yes",
        lambda: f.unknown_domain_default(indexes_exist=True),
        "add.effective_default_unknown",
        MAY_FAIL,
        POSSIBLE,
        POSSIBLE,
        POSSIBLE,
        Risk.CRITICAL,
    ),
    (
        "unknown domain default, indexes=no",
        lambda: f.unknown_domain_default(indexes_exist=False),
        "add.effective_default_unknown",
        MAY_FAIL,
        POSSIBLE,
        POSSIBLE,
        NO,
        Risk.CRITICAL,
    ),
    (
        "constrained domain, indexes=yes",
        lambda: f.constrained_domain(indexes_exist=True),
        "add.domain_with_constraints",
        APPLIES,
        YES,
        YES,
        YES,
        Risk.CRITICAL,
    ),
    (
        "constrained domain, indexes=no",
        lambda: f.constrained_domain(indexes_exist=False),
        "add.domain_with_constraints",
        APPLIES,
        YES,
        YES,
        NO,
        Risk.CRITICAL,
    ),
    (
        "pg_catalog.now() timestamptz, provolatile=s",
        f.now_default,
        "add.nullable.const_or_nonvolatile_valid",
        APPLIES,
        NO,
        NO,
        NO,
        Risk.WARNING,
    ),
    (
        "A3 pg_catalog.clock_timestamp(), indexes=yes",
        lambda: f.clock_timestamp_default(indexes_exist=True),
        "add.volatile_valid",
        APPLIES,
        YES,
        YES,
        YES,
        Risk.CRITICAL,
    ),
    (
        "pg_catalog.clock_timestamp(), indexes=no",
        lambda: f.clock_timestamp_default(indexes_exist=False),
        "add.volatile_valid",
        APPLIES,
        YES,
        YES,
        NO,
        Risk.CRITICAL,
    ),
    (
        "explicit DEFAULT NULL, nullable",
        f.explicit_default_null,
        "add.nullable.no_default",
        APPLIES,
        NO,
        NO,
        NO,
        Risk.WARNING,
    ),
    (
        "NOT NULL + proven non-null nonvolatile default",
        f.not_null_proven_nonnull_default,
        "add.not_null.nonvolatile_valid.proven_nonnull",
        APPLIES,
        NO,
        NO,
        NO,
        Risk.WARNING,
    ),
    (
        "A4 NOT NULL, effective_default NULL",
        f.a4_not_null_no_default,
        "add.not_null.no_default",
        MAY_FAIL,
        NO,
        POSSIBLE,
        NO,
        Risk.CRITICAL,
    ),
    (
        "A5 NOT NULL, effective_default NULL, n_live_tup=0",
        f.a5_not_null_no_default_empty_stats,
        "add.not_null.no_default",
        MAY_FAIL,
        NO,
        POSSIBLE,
        NO,
        Risk.CRITICAL,
    ),
    (
        "NOT NULL + default whose nullability is unknown",
        f.not_null_unknown_nullability_default,
        "add.not_null.nullability_null_or_unknown",
        MAY_FAIL,
        NO,
        POSSIBLE,
        NO,
        Risk.CRITICAL,
    ),
)


def _semantic_projection(verdict: RuleVerdict) -> dict[str, Any]:
    """The comparable part of a verdict (plan Task 8: not full card identity)."""
    return {
        "execution_prediction": verdict.execution_prediction,
        "risk": verdict.risk,
        "lock": verdict.lock,
        "table_rewrite": verdict.table_rewrite,
        "table_scan": verdict.table_scan,
        "index_rebuild": verdict.index_rebuild,
        "rule_key": verdict.rule_key,
        "evidence_ids": verdict.evidence_ids,
        "limitations": verdict.limitations,
    }


@pytest.mark.parametrize(
    ("build", "rule_key", "execution", "rewrite", "scan", "index_rebuild", "risk"),
    [row[1:] for row in MANDATORY_MATRIX],
    ids=[row[0] for row in MANDATORY_MATRIX],
)
def test_mandatory_matrix_row(
    build: Callable[[], AddColumnFacts],
    rule_key: str,
    execution: ExecutionPrediction,
    rewrite: PhysicalTriState,
    scan: PhysicalTriState,
    index_rebuild: PhysicalTriState,
    risk: Risk,
) -> None:
    verdict = evaluate_add_column(build())

    assert verdict.rule_key == rule_key
    assert verdict.execution_prediction is execution
    assert verdict.table_rewrite is rewrite
    assert verdict.table_scan is scan
    assert verdict.index_rebuild is index_rebuild
    assert verdict.risk is risk


@pytest.mark.parametrize(
    "build", [row[1] for row in MANDATORY_MATRIX], ids=[row[0] for row in MANDATORY_MATRIX]
)
def test_every_matrix_row_is_analyzed_under_access_exclusive_lock(
    build: Callable[[], AddColumnFacts],
) -> None:
    verdict = evaluate_add_column(build())

    assert verdict.analysis_status is AnalysisStatus.ANALYZED
    assert verdict.lock is LockMode.ACCESS_EXCLUSIVE_LOCK
    assert verdict.no_op_reason is None


@pytest.mark.parametrize(
    "build", [row[1] for row in MANDATORY_MATRIX], ids=[row[0] for row in MANDATORY_MATRIX]
)
def test_every_matrix_row_reports_the_authorization_limitation(
    build: Callable[[], AddColumnFacts],
) -> None:
    assert AUTHORIZATION_LIMITATION in evaluate_add_column(build()).limitations


@pytest.mark.parametrize(
    "build", [row[1] for row in MANDATORY_MATRIX], ids=[row[0] for row in MANDATORY_MATRIX]
)
def test_every_matrix_row_cites_its_own_rule_first(build: Callable[[], AddColumnFacts]) -> None:
    verdict = evaluate_add_column(build())

    assert verdict.evidence_ids[0] == f"rule:{verdict.rule_key}"


@pytest.mark.parametrize(
    "build", [row[1] for row in MANDATORY_MATRIX], ids=[row[0] for row in MANDATORY_MATRIX]
)
def test_every_matrix_row_explains_itself(build: Callable[[], AddColumnFacts]) -> None:
    assert all(line.strip() for line in evaluate_add_column(build()).why)


@pytest.mark.parametrize(
    "build", [row[1] for row in MANDATORY_MATRIX], ids=[row[0] for row in MANDATORY_MATRIX]
)
def test_confirmed_rewrite_always_implies_confirmed_scan(
    build: Callable[[], AddColumnFacts],
) -> None:
    verdict = evaluate_add_column(build())

    if verdict.table_rewrite is YES:
        assert verdict.table_scan is YES


# --- now() vs clock_timestamp() ------------------------------------------------


def test_now_is_classified_stable_and_clock_timestamp_volatile() -> None:
    assert f.classify_volatility(f.NOW) == "proven_nonvolatile"
    assert f.classify_volatility(f.CLOCK_TIMESTAMP) == "proven_volatile"


def test_now_default_does_not_rewrite_but_clock_timestamp_does() -> None:
    now = evaluate_add_column(f.now_default())
    clock = evaluate_add_column(f.clock_timestamp_default(indexes_exist=True))

    assert (now.rule_key, now.table_rewrite, now.table_scan, now.risk) == (
        "add.nullable.const_or_nonvolatile_valid",
        NO,
        NO,
        Risk.WARNING,
    )
    assert (clock.rule_key, clock.table_rewrite, clock.table_scan, clock.risk) == (
        "add.volatile_valid",
        YES,
        YES,
        Risk.CRITICAL,
    )


def test_only_the_volatile_default_makes_indexes_matter() -> None:
    """`now()` leaves indexes alone even though the same table has one."""
    now = evaluate_add_column(f.now_default())
    clock = evaluate_add_column(f.clock_timestamp_default(indexes_exist=True))

    assert now.index_rebuild is NO
    assert clock.index_rebuild is YES
    assert "index:impact_a3_id_idx" in clock.evidence_ids
    assert not any(eid.startswith("index:") for eid in now.evidence_ids)


def test_volatile_default_cites_the_resolved_function() -> None:
    verdict = evaluate_add_column(f.clock_timestamp_default(indexes_exist=True))

    assert verdict.evidence_ids == (
        "rule:add.volatile_valid",
        "function:pg_catalog.clock_timestamp()",
        "index:impact_a3_id_idx",
    )


# --- A4 / A5 -------------------------------------------------------------------


def test_a4_and_a5_have_identical_semantic_projections() -> None:
    a4 = evaluate_add_column(f.a4_not_null_no_default())
    a5 = evaluate_add_column(f.a5_not_null_no_default_empty_stats())

    assert _semantic_projection(a4) == _semantic_projection(a5)


def test_a4_and_a5_are_not_required_to_be_byte_identical() -> None:
    """Only the projection is pinned; `impact_scale` still tracks metric presence."""
    a4 = evaluate_add_column(f.a4_not_null_no_default())
    a5 = evaluate_add_column(f.a5_not_null_no_default_empty_stats())

    assert a4.confidence.impact_scale is ImpactScaleConfidence.LOW
    assert a5.confidence.impact_scale is ImpactScaleConfidence.MEDIUM


@pytest.mark.parametrize("n_live_tup", [None, 0, 1, 10_000_000])
def test_n_live_tup_never_flips_the_not_null_verdict(n_live_tup: int | None) -> None:
    baseline = evaluate_add_column(f.a5_not_null_no_default_empty_stats())
    verdict = evaluate_add_column(
        dataclasses.replace(f.a5_not_null_no_default_empty_stats(), n_live_tup=n_live_tup)
    )

    assert verdict == baseline


@pytest.mark.parametrize(
    "build",
    [f.a4_not_null_no_default, f.a5_not_null_no_default_empty_stats],
    ids=["A4", "A5"],
)
def test_a4_a5_limitations_are_emptiness_then_authorization(
    build: Callable[[], AddColumnFacts],
) -> None:
    assert evaluate_add_column(build()).limitations == (
        TABLE_EMPTINESS_LIMITATION,
        AUTHORIZATION_LIMITATION,
    )


def test_emptiness_limitation_is_the_exact_design_text() -> None:
    assert TABLE_EMPTINESS_LIMITATION == (
        "Table emptiness is not proven from catalog evidence (n_live_tup is an estimate)."
    )


def test_emptiness_limitation_is_absent_when_not_null_is_satisfied() -> None:
    verdict = evaluate_add_column(f.not_null_proven_nonnull_default())

    assert verdict.limitations == (AUTHORIZATION_LIMITATION,)


def test_emptiness_limitation_is_absent_for_nullable_columns() -> None:
    verdict = evaluate_add_column(f.a1_nullable_no_default())

    assert verdict.limitations == (AUTHORIZATION_LIMITATION,)


# --- precedence ----------------------------------------------------------------


def test_invalid_coercion_outranks_a_constrained_domain() -> None:
    facts = dataclasses.replace(
        f.constrained_domain(indexes_exist=True), default_coercion="proven_invalid"
    )
    verdict = evaluate_add_column(facts)

    assert verdict.rule_key == "add.coercion_invalid"
    assert verdict.execution_prediction is WOULD_FAIL
    assert verdict.table_rewrite is NOT_APPLICABLE


def test_constrained_domain_outranks_an_unclassifiable_default() -> None:
    facts = dataclasses.replace(
        f.constrained_domain(indexes_exist=True),
        default_volatility="unknown",
        default_coercion="unknown",
    )

    assert evaluate_add_column(facts).rule_key == "add.domain_with_constraints"


def test_constrained_domain_outranks_the_not_null_rows() -> None:
    facts = dataclasses.replace(f.constrained_domain(indexes_exist=False), nullable=False)
    verdict = evaluate_add_column(facts)

    assert verdict.rule_key == "add.domain_with_constraints"
    assert verdict.execution_prediction is APPLIES


def test_unclassifiable_default_outranks_the_not_null_rows() -> None:
    facts = dataclasses.replace(f.unknown_domain_default(indexes_exist=False), nullable=False)

    assert evaluate_add_column(facts).rule_key == "add.effective_default_unknown"


def test_volatile_default_outranks_the_not_null_rows() -> None:
    facts = dataclasses.replace(f.clock_timestamp_default(indexes_exist=False), nullable=False)
    verdict = evaluate_add_column(facts)

    assert verdict.rule_key == "add.volatile_valid"
    assert verdict.execution_prediction is APPLIES


def test_an_unwritten_default_is_never_no_default_when_the_domain_supplies_one() -> None:
    """Design section 3.7: a domain default must not be collapsed into `no_default`."""
    verdict = evaluate_add_column(f.nullable_domain_default_nonvolatile())

    assert verdict.rule_key == "add.nullable.const_or_nonvolatile_valid"


# --- server majors -------------------------------------------------------------


@pytest.mark.parametrize("server_major", f.SERVER_MAJORS)
@pytest.mark.parametrize("indexes_exist", [True, False])
def test_constrained_domain_applies_to_every_supported_major(
    server_major: int, indexes_exist: bool
) -> None:
    facts = dataclasses.replace(
        f.constrained_domain(indexes_exist=indexes_exist), server_major=server_major
    )
    verdict = evaluate_add_column(facts)

    assert verdict.rule_key == "add.domain_with_constraints"
    assert verdict.table_rewrite is YES
    assert verdict.table_scan is YES
    assert verdict.index_rebuild is (YES if indexes_exist else NO)
    assert verdict.risk is Risk.CRITICAL


@pytest.mark.parametrize("server_major", f.SERVER_MAJORS)
def test_the_whole_matrix_is_major_independent(server_major: int) -> None:
    for _label, build, *_rest in MANDATORY_MATRIX:
        baseline = evaluate_add_column(build())
        shifted = evaluate_add_column(dataclasses.replace(build(), server_major=server_major))
        assert _semantic_projection(shifted) == _semantic_projection(baseline)


@pytest.mark.parametrize("server_major", [13, 19, 0])
def test_unsupported_server_majors_are_rejected(server_major: int) -> None:
    with pytest.raises(ValueError, match="unsupported server major"):
        dataclasses.replace(f.a1_nullable_no_default(), server_major=server_major)


# --- shape ---------------------------------------------------------------------


def test_confidence_is_high_on_every_catalog_proven_axis() -> None:
    confidence = evaluate_add_column(f.a1_nullable_no_default()).confidence

    assert confidence.lock is ConfidenceLevel.HIGH
    assert confidence.rewrite is ConfidenceLevel.HIGH
    assert confidence.execution is ConfidenceLevel.HIGH
    assert confidence.dependencies is ConfidenceLevel.HIGH


def test_constrained_domain_cites_the_domain_and_its_constraints() -> None:
    verdict = evaluate_add_column(f.constrained_domain(indexes_exist=True))

    assert verdict.evidence_ids == (
        "rule:add.domain_with_constraints",
        "type:public.positive_amount",
        "domain_constraint:positive_amount_check",
        "index:t_id_idx",
    )


def test_indexes_are_not_cited_when_nothing_is_rebuilt() -> None:
    verdict = evaluate_add_column(f.coercion_invalid(indexes_exist=True))

    assert verdict.evidence_ids == ("rule:add.coercion_invalid",)


def test_evaluation_is_deterministic() -> None:
    for _label, build, *_rest in MANDATORY_MATRIX:
        assert evaluate_add_column(build()) == evaluate_add_column(build())


def test_add_column_module_does_not_import_psycopg() -> None:
    tree = ast.parse(Path(add_column_module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "psycopg"
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] != "psycopg"
