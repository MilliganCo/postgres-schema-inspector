"""Full TYPE rule matrix (plan Task 7, design section 3.6).

`MATRIX` below is the executable copy of the normative table: each entry is
the *only* allowed verdict for its facts, and `test_matrix_row` asserts every
semantic field at once so a change in one column cannot be absorbed by
another.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from pginspect.impact.models.card import ImpactConfidence
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ConfidenceLevel,
    ExecutionPrediction,
    ImpactScaleConfidence,
    LockMode,
    PhysicalTriState,
    Risk,
)
from pginspect.impact.rules.contracts import AUTHORIZATION_LIMITATION
from pginspect.impact.rules.type_change import (
    RULE_ASSIGNMENT_CAST_UNKNOWN,
    RULE_COLLATION_CHANGE,
    RULE_DOMAIN_BOUNDARY,
    RULE_NO_ASSIGNMENT_CAST,
    RULE_OPAQUE_USING,
    RULE_PROVEN_REWRITE,
    RULE_SAME_DECLARED_TYPE,
    RULE_TYPMOD_CHANGE,
    TypeChangeFacts,
    binary_rule_key,
    evaluate_type_change,
)
from . import factories_type as f

APPLIES = ExecutionPrediction.APPLIES
MAY_FAIL = ExecutionPrediction.MAY_FAIL
WOULD_FAIL = ExecutionPrediction.WOULD_FAIL

YES = PhysicalTriState.YES
NO = PhysicalTriState.NO
POSSIBLE = PhysicalTriState.POSSIBLE
NOT_APPLICABLE = PhysicalTriState.NOT_APPLICABLE

AE = LockMode.ACCESS_EXCLUSIVE_LOCK

CRITICAL = Risk.CRITICAL
WARNING = Risk.WARNING

RULE_BINARY_TEXT_TO_VARCHAR = "type.binary.text_to_varchar.same_collation.no_domain.no_using"

COERCION_INTEGER_TO_TEXT = "coercion:integer_to_text_assignment"
COERCION_TEXT_TO_VARCHAR = "coercion:text_to_varchar_binary"


@dataclass(frozen=True)
class Expected:
    rule_key: str
    execution: ExecutionPrediction
    rewrite: PhysicalTriState
    scan: PhysicalTriState
    index_rebuild: PhysicalTriState
    risk: Risk
    lock: LockMode = AE


MATRIX: tuple[tuple[str, TypeChangeFacts, Expected], ...] = (
    (
        "same-declared-type-no-using",
        f.same_declared_type_no_using(),
        Expected(RULE_SAME_DECLARED_TYPE, APPLIES, NO, NO, NO, WARNING),
    ),
    (
        "unknown-assignment-indexes",
        f.unknown_assignment_cast(affected_indexes_exist=True),
        Expected(RULE_ASSIGNMENT_CAST_UNKNOWN, MAY_FAIL, POSSIBLE, POSSIBLE, POSSIBLE, CRITICAL),
    ),
    (
        "unknown-assignment-no-indexes",
        f.unknown_assignment_cast(affected_indexes_exist=False),
        Expected(RULE_ASSIGNMENT_CAST_UNKNOWN, MAY_FAIL, POSSIBLE, POSSIBLE, NO, CRITICAL),
    ),
    (
        "opaque-using-indexes",
        f.opaque_using(affected_indexes_exist=True),
        Expected(RULE_OPAQUE_USING, MAY_FAIL, POSSIBLE, POSSIBLE, POSSIBLE, CRITICAL),
    ),
    (
        "opaque-using-no-indexes",
        f.opaque_using(affected_indexes_exist=False),
        Expected(RULE_OPAQUE_USING, MAY_FAIL, POSSIBLE, POSSIBLE, NO, CRITICAL),
    ),
    (
        "proven-rewrite-integer-to-text-indexes",
        f.proven_rewrite_integer_to_text(affected_indexes_exist=True),
        Expected(RULE_PROVEN_REWRITE, APPLIES, YES, YES, YES, CRITICAL),
    ),
    (
        "proven-rewrite-integer-to-text-no-indexes",
        f.proven_rewrite_integer_to_text(affected_indexes_exist=False),
        Expected(RULE_PROVEN_REWRITE, APPLIES, YES, YES, NO, CRITICAL),
    ),
    (
        "binary-text-to-varchar-pg14-indexes",
        f.binary_text_to_varchar(server_major=14, affected_indexes_exist=True),
        Expected(RULE_BINARY_TEXT_TO_VARCHAR, APPLIES, NO, NO, YES, CRITICAL),
    ),
    (
        "binary-text-to-varchar-pg15-indexes",
        f.binary_text_to_varchar(server_major=15, affected_indexes_exist=True),
        Expected(RULE_BINARY_TEXT_TO_VARCHAR, APPLIES, NO, NO, NO, WARNING),
    ),
    (
        "binary-text-to-varchar-pg16-indexes",
        f.binary_text_to_varchar(server_major=16, affected_indexes_exist=True),
        Expected(RULE_BINARY_TEXT_TO_VARCHAR, APPLIES, NO, NO, NO, WARNING),
    ),
    (
        "binary-text-to-varchar-pg17-indexes",
        f.binary_text_to_varchar(server_major=17, affected_indexes_exist=True),
        Expected(RULE_BINARY_TEXT_TO_VARCHAR, APPLIES, NO, NO, NO, WARNING),
    ),
    (
        "binary-text-to-varchar-pg18-indexes",
        f.binary_text_to_varchar(server_major=18, affected_indexes_exist=True),
        Expected(RULE_BINARY_TEXT_TO_VARCHAR, APPLIES, NO, NO, NO, WARNING),
    ),
    (
        "binary-text-to-varchar-pg14-no-indexes",
        f.binary_text_to_varchar(server_major=14, affected_indexes_exist=False),
        Expected(RULE_BINARY_TEXT_TO_VARCHAR, APPLIES, NO, NO, NO, WARNING),
    ),
    (
        "binary-text-to-varchar-pg15-no-indexes",
        f.binary_text_to_varchar(server_major=15, affected_indexes_exist=False),
        Expected(RULE_BINARY_TEXT_TO_VARCHAR, APPLIES, NO, NO, NO, WARNING),
    ),
    (
        "binary-text-to-varchar-pg16-no-indexes",
        f.binary_text_to_varchar(server_major=16, affected_indexes_exist=False),
        Expected(RULE_BINARY_TEXT_TO_VARCHAR, APPLIES, NO, NO, NO, WARNING),
    ),
    (
        "binary-text-to-varchar-pg17-no-indexes",
        f.binary_text_to_varchar(server_major=17, affected_indexes_exist=False),
        Expected(RULE_BINARY_TEXT_TO_VARCHAR, APPLIES, NO, NO, NO, WARNING),
    ),
    (
        "binary-text-to-varchar-pg18-no-indexes",
        f.binary_text_to_varchar(server_major=18, affected_indexes_exist=False),
        Expected(RULE_BINARY_TEXT_TO_VARCHAR, APPLIES, NO, NO, NO, WARNING),
    ),
    (
        "no-assignment-cast-text-to-integer",
        f.no_assignment_cast_text_to_integer(),
        Expected(
            RULE_NO_ASSIGNMENT_CAST,
            WOULD_FAIL,
            NOT_APPLICABLE,
            NOT_APPLICABLE,
            NOT_APPLICABLE,
            CRITICAL,
        ),
    ),
    (
        "typmod-widen-indexes",
        f.typmod_widen(affected_indexes_exist=True),
        Expected(RULE_TYPMOD_CHANGE, MAY_FAIL, POSSIBLE, POSSIBLE, POSSIBLE, CRITICAL),
    ),
    (
        "typmod-widen-no-indexes",
        f.typmod_widen(affected_indexes_exist=False),
        Expected(RULE_TYPMOD_CHANGE, MAY_FAIL, POSSIBLE, POSSIBLE, NO, CRITICAL),
    ),
    (
        "typmod-narrow-indexes",
        f.typmod_narrow(affected_indexes_exist=True),
        Expected(RULE_TYPMOD_CHANGE, MAY_FAIL, POSSIBLE, POSSIBLE, POSSIBLE, CRITICAL),
    ),
    (
        "typmod-narrow-no-indexes",
        f.typmod_narrow(affected_indexes_exist=False),
        Expected(RULE_TYPMOD_CHANGE, MAY_FAIL, POSSIBLE, POSSIBLE, NO, CRITICAL),
    ),
    (
        "collation-change-indexes",
        f.collation_change_only(affected_indexes_exist=True),
        Expected(RULE_COLLATION_CHANGE, MAY_FAIL, POSSIBLE, POSSIBLE, POSSIBLE, CRITICAL),
    ),
    (
        "collation-change-no-indexes",
        f.collation_change_only(affected_indexes_exist=False),
        Expected(RULE_COLLATION_CHANGE, MAY_FAIL, POSSIBLE, POSSIBLE, NO, CRITICAL),
    ),
    (
        "domain-source-to-base-indexes",
        f.domain_source_to_base(affected_indexes_exist=True),
        Expected(RULE_DOMAIN_BOUNDARY, MAY_FAIL, POSSIBLE, POSSIBLE, POSSIBLE, CRITICAL),
    ),
    (
        "domain-source-to-base-no-indexes",
        f.domain_source_to_base(affected_indexes_exist=False),
        Expected(RULE_DOMAIN_BOUNDARY, MAY_FAIL, POSSIBLE, POSSIBLE, NO, CRITICAL),
    ),
    (
        "base-to-domain-target-indexes",
        f.base_to_domain_target(affected_indexes_exist=True),
        Expected(RULE_DOMAIN_BOUNDARY, MAY_FAIL, POSSIBLE, POSSIBLE, POSSIBLE, CRITICAL),
    ),
    (
        "base-to-domain-target-no-indexes",
        f.base_to_domain_target(affected_indexes_exist=False),
        Expected(RULE_DOMAIN_BOUNDARY, MAY_FAIL, POSSIBLE, POSSIBLE, NO, CRITICAL),
    ),
)

MATRIX_PARAMS = [pytest.param(facts, expected, id=case_id) for case_id, facts, expected in MATRIX]


def _all_facts() -> tuple[TypeChangeFacts, ...]:
    return tuple(facts for _, facts, _ in MATRIX)


@pytest.mark.parametrize(("facts", "expected"), MATRIX_PARAMS)
def test_matrix_row(facts: TypeChangeFacts, expected: Expected) -> None:
    verdict = evaluate_type_change(facts)
    assert verdict.rule_key == expected.rule_key
    assert verdict.analysis_status is AnalysisStatus.ANALYZED
    assert verdict.execution_prediction is expected.execution
    assert verdict.table_rewrite is expected.rewrite
    assert verdict.table_scan is expected.scan
    assert verdict.index_rebuild is expected.index_rebuild
    assert verdict.risk is expected.risk
    assert verdict.lock is expected.lock


@pytest.mark.parametrize("facts", _all_facts())
def test_every_analyzed_verdict_carries_the_authorization_limitation(
    facts: TypeChangeFacts,
) -> None:
    assert evaluate_type_change(facts).limitations == (AUTHORIZATION_LIMITATION,)


@pytest.mark.parametrize("facts", _all_facts())
def test_every_verdict_cites_its_own_rule_key(facts: TypeChangeFacts) -> None:
    verdict = evaluate_type_change(facts)
    assert f"rule:{verdict.rule_key}" in verdict.evidence_ids


@pytest.mark.parametrize("facts", _all_facts())
def test_every_verdict_explains_itself(facts: TypeChangeFacts) -> None:
    assert evaluate_type_change(facts).why != ()


@pytest.mark.parametrize("facts", _all_facts())
def test_no_matrix_row_reports_unsupported_evidence(facts: TypeChangeFacts) -> None:
    assert evaluate_type_change(facts).analysis_status is not AnalysisStatus.UNSUPPORTED_EVIDENCE


@pytest.mark.parametrize("facts", _all_facts())
def test_confirmed_rewrite_always_implies_confirmed_scan(facts: TypeChangeFacts) -> None:
    verdict = evaluate_type_change(facts)
    if verdict.table_rewrite is YES:
        assert verdict.table_scan is YES


@pytest.mark.parametrize("facts", _all_facts())
def test_evidence_ids_are_unique(facts: TypeChangeFacts) -> None:
    evidence_ids = evaluate_type_change(facts).evidence_ids
    assert len(set(evidence_ids)) == len(evidence_ids)


@pytest.mark.parametrize("facts", _all_facts())
def test_no_matrix_row_reports_a_no_op(facts: TypeChangeFacts) -> None:
    assert evaluate_type_change(facts).no_op_reason is None


def test_matrix_covers_every_rule_key() -> None:
    assert {expected.rule_key for _, _, expected in MATRIX} == {
        RULE_SAME_DECLARED_TYPE,
        RULE_ASSIGNMENT_CAST_UNKNOWN,
        RULE_OPAQUE_USING,
        RULE_PROVEN_REWRITE,
        RULE_BINARY_TEXT_TO_VARCHAR,
        RULE_NO_ASSIGNMENT_CAST,
        RULE_TYPMOD_CHANGE,
        RULE_COLLATION_CHANGE,
        RULE_DOMAIN_BOUNDARY,
    }


def test_matrix_case_ids_are_unique() -> None:
    case_ids = [case_id for case_id, _, _ in MATRIX]
    assert len(set(case_ids)) == len(case_ids)


# --- Coercion evidence (T1 / T2 / T3) ---------------------------------------


@pytest.mark.parametrize("affected_indexes_exist", [True, False])
def test_t1_cites_the_integer_to_text_coercion_evidence(affected_indexes_exist: bool) -> None:
    verdict = evaluate_type_change(
        f.proven_rewrite_integer_to_text(affected_indexes_exist=affected_indexes_exist)
    )
    assert verdict.evidence_ids == (
        f"rule:{RULE_PROVEN_REWRITE}",
        COERCION_INTEGER_TO_TEXT,
    )


@pytest.mark.parametrize("server_major", f.SUPPORTED_MAJORS)
def test_t2_cites_the_binary_coercion_evidence(server_major: int) -> None:
    verdict = evaluate_type_change(
        f.binary_text_to_varchar(server_major=server_major, affected_indexes_exist=True)
    )
    assert verdict.evidence_ids == (
        f"rule:{RULE_BINARY_TEXT_TO_VARCHAR}",
        COERCION_TEXT_TO_VARCHAR,
    )


def test_t3_cites_only_its_checked_in_rule() -> None:
    verdict = evaluate_type_change(f.no_assignment_cast_text_to_integer())
    assert verdict.evidence_ids == (f"rule:{RULE_NO_ASSIGNMENT_CAST}",)


def test_t2_without_a_live_binary_pg_cast_row_falls_back_to_unknown() -> None:
    """A missing binary row must never be assumed; it degrades conservatively."""
    facts = f.binary_text_to_varchar(server_major=16, affected_indexes_exist=True)
    without_row = TypeChangeFacts(
        server_major=facts.server_major,
        source_type_name=facts.source_type_name,
        target_type_name=facts.target_type_name,
        source_typmod=facts.source_typmod,
        target_typmod=facts.target_typmod,
        source_collation_oid=facts.source_collation_oid,
        target_collation_oid=facts.target_collation_oid,
        source_is_domain=facts.source_is_domain,
        target_is_domain=facts.target_is_domain,
        using_present=facts.using_present,
        using_identity_proven=facts.using_identity_proven,
        affected_indexes_exist=facts.affected_indexes_exist,
        metrics_present=facts.metrics_present,
        pg_cast_rows=(),
        table_exists=facts.table_exists,
    )
    verdict = evaluate_type_change(without_row)
    assert verdict.rule_key == RULE_ASSIGNMENT_CAST_UNKNOWN
    assert verdict.analysis_status is AnalysisStatus.ANALYZED
    assert verdict.execution_prediction is MAY_FAIL
    assert verdict.risk is CRITICAL


# --- PG14 vs PG15-18 binary index-rebuild boundary --------------------------


@pytest.mark.parametrize("server_major", f.SUPPORTED_MAJORS)
def test_binary_index_rebuild_boundary_with_indexes(server_major: int) -> None:
    verdict = evaluate_type_change(
        f.binary_text_to_varchar(server_major=server_major, affected_indexes_exist=True)
    )
    if server_major == 14:
        assert verdict.index_rebuild is YES
        assert verdict.risk is CRITICAL
    else:
        assert verdict.index_rebuild is NO
        assert verdict.risk is WARNING


@pytest.mark.parametrize("server_major", f.SUPPORTED_MAJORS)
def test_binary_without_indexes_never_rebuilds_on_any_major(server_major: int) -> None:
    verdict = evaluate_type_change(
        f.binary_text_to_varchar(server_major=server_major, affected_indexes_exist=False)
    )
    assert verdict.index_rebuild is NO
    assert verdict.risk is WARNING


@pytest.mark.parametrize("server_major", f.SUPPORTED_MAJORS)
def test_binary_never_rewrites_or_scans_on_any_major(server_major: int) -> None:
    verdict = evaluate_type_change(
        f.binary_text_to_varchar(server_major=server_major, affected_indexes_exist=True)
    )
    assert verdict.table_rewrite is NO
    assert verdict.table_scan is NO


def test_binary_rule_key_is_built_from_the_normalized_pair() -> None:
    assert binary_rule_key("  TEXT ", "VarChar") == RULE_BINARY_TEXT_TO_VARCHAR


# --- Precedence -------------------------------------------------------------


def test_opaque_using_outranks_cast_classification() -> None:
    """The same pair is T3 without USING and opaque with one."""
    assert evaluate_type_change(f.no_assignment_cast_text_to_integer()).rule_key == (
        RULE_NO_ASSIGNMENT_CAST
    )
    assert evaluate_type_change(f.opaque_using(affected_indexes_exist=False)).rule_key == (
        RULE_OPAQUE_USING
    )


def test_identity_proven_using_does_not_trigger_the_opaque_rule() -> None:
    facts = f.same_declared_type_no_using()
    with_identity_using = TypeChangeFacts(
        server_major=facts.server_major,
        source_type_name=facts.source_type_name,
        target_type_name=facts.target_type_name,
        source_typmod=facts.source_typmod,
        target_typmod=facts.target_typmod,
        source_collation_oid=facts.source_collation_oid,
        target_collation_oid=facts.target_collation_oid,
        source_is_domain=facts.source_is_domain,
        target_is_domain=facts.target_is_domain,
        using_present=True,
        using_identity_proven=True,
        affected_indexes_exist=facts.affected_indexes_exist,
        metrics_present=facts.metrics_present,
        pg_cast_rows=facts.pg_cast_rows,
        table_exists=facts.table_exists,
    )
    assert evaluate_type_change(with_identity_using).rule_key == RULE_SAME_DECLARED_TYPE


def test_domain_boundary_outranks_collation_and_typmod() -> None:
    facts = TypeChangeFacts(
        server_major=16,
        source_type_name=f.DOMAIN_TYPE_NAME,
        target_type_name="varchar",
        source_typmod=f.varchar_typmod(10),
        target_typmod=f.varchar_typmod(20),
        source_collation_oid=f.DEFAULT_COLLATION_OID,
        target_collation_oid=f.C_COLLATION_OID,
        source_is_domain=True,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=True,
        metrics_present=True,
        pg_cast_rows=(),
        table_exists=True,
    )
    assert evaluate_type_change(facts).rule_key == RULE_DOMAIN_BOUNDARY


def test_collation_outranks_typmod() -> None:
    facts = TypeChangeFacts(
        server_major=16,
        source_type_name="varchar",
        target_type_name="varchar",
        source_typmod=f.varchar_typmod(10),
        target_typmod=f.varchar_typmod(20),
        source_collation_oid=f.DEFAULT_COLLATION_OID,
        target_collation_oid=f.C_COLLATION_OID,
        source_is_domain=False,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=True,
        metrics_present=True,
        pg_cast_rows=(),
        table_exists=True,
    )
    assert evaluate_type_change(facts).rule_key == RULE_COLLATION_CHANGE


def test_non_collatable_source_is_not_read_as_a_collation_change() -> None:
    """`integer -> text` gains a collation, but that is a type change, not a recollation."""
    verdict = evaluate_type_change(f.proven_rewrite_integer_to_text(affected_indexes_exist=False))
    assert verdict.rule_key == RULE_PROVEN_REWRITE


def test_declared_type_name_comparison_is_normalized() -> None:
    facts = TypeChangeFacts(
        server_major=16,
        source_type_name="VARCHAR",
        target_type_name="  varchar  ",
        source_typmod=f.varchar_typmod(50),
        target_typmod=f.varchar_typmod(50),
        source_collation_oid=f.DEFAULT_COLLATION_OID,
        target_collation_oid=f.DEFAULT_COLLATION_OID,
        source_is_domain=False,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=False,
        metrics_present=True,
        pg_cast_rows=(),
        table_exists=True,
    )
    assert evaluate_type_change(facts).rule_key == RULE_SAME_DECLARED_TYPE


# --- Lock -------------------------------------------------------------------


@pytest.mark.parametrize("facts", _all_facts())
def test_lock_is_access_exclusive_whenever_the_table_exists(facts: TypeChangeFacts) -> None:
    assert facts.table_exists is True
    assert evaluate_type_change(facts).lock is AE


def test_would_fail_without_the_table_reports_no_applicable_lock() -> None:
    verdict = evaluate_type_change(f.no_assignment_cast_text_to_integer(table_exists=False))
    assert verdict.rule_key == RULE_NO_ASSIGNMENT_CAST
    assert verdict.execution_prediction is WOULD_FAIL
    assert verdict.lock is LockMode.NOT_APPLICABLE
    assert verdict.risk is CRITICAL


# --- Confidence -------------------------------------------------------------


@pytest.mark.parametrize("facts", _all_facts())
def test_analyzed_verdicts_are_high_confidence_on_every_semantic_axis(
    facts: TypeChangeFacts,
) -> None:
    confidence = evaluate_type_change(facts).confidence
    assert confidence.lock is ConfidenceLevel.HIGH
    assert confidence.rewrite is ConfidenceLevel.HIGH
    assert confidence.execution is ConfidenceLevel.HIGH
    assert confidence.dependencies is ConfidenceLevel.HIGH


@pytest.mark.parametrize("facts", _all_facts())
def test_impact_scale_is_medium_when_metrics_are_present(facts: TypeChangeFacts) -> None:
    assert facts.metrics_present is True
    assert evaluate_type_change(facts).confidence.impact_scale is ImpactScaleConfidence.MEDIUM


def test_impact_scale_drops_to_low_without_metrics() -> None:
    verdict = evaluate_type_change(f.same_declared_type_no_using(metrics_present=False))
    assert verdict.confidence.impact_scale is ImpactScaleConfidence.LOW
    assert verdict.confidence.lock is ConfidenceLevel.HIGH


def test_confidence_is_the_shared_public_contract() -> None:
    verdict = evaluate_type_change(f.same_declared_type_no_using())
    assert isinstance(verdict.confidence, ImpactConfidence)


# --- Purity boundary --------------------------------------------------------


def _rules_source_files() -> tuple[Path, ...]:
    root = Path(__file__).resolve().parents[4] / "src" / "pginspect" / "impact" / "rules"
    return tuple(sorted(root.rglob("*.py")))


def test_type_change_module_does_not_import_psycopg() -> None:
    modules = [p for p in _rules_source_files() if p.name == "type_change.py"]
    assert modules, "type_change.py not found under impact/rules"
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "psycopg"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] != "psycopg"


def test_no_rules_module_imports_psycopg() -> None:
    offenders: list[str] = []
    for module in _rules_source_files():
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name.split(".")[0] == "psycopg" for alias in node.names):
                    offenders.append(module.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] == "psycopg":
                    offenders.append(module.name)
    assert offenders == []


def test_evaluate_type_change_is_deterministic() -> None:
    for _, facts, _ in MATRIX:
        assert evaluate_type_change(facts) == evaluate_type_change(facts)
