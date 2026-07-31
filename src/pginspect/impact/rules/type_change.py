"""TYPE rule engine — full normative matrix (plan Task 7, design section 3.6).

`evaluate_type_change` is a pure function over `TypeChangeFacts`: no catalog
query, no session, no psycopg. Every fact the matrix branches on is already
resolved by the caller (Task 5 catalog capture) and handed over as a frozen
value object, so the same facts always produce the same verdict.

Decision precedence (first match wins):

1. opaque ``USING`` — an expression the analyzer cannot prove is the identity
   can do anything to every row, so it outranks any cast classification;
2. domain boundary — crossing into or out of a domain adds constraint checks
   the cast tables do not describe;
3. collation change — a different collation reorders every btree index;
4. typmod change — deliberately conservative in both directions, there is no
   silent "safe widen" in this matrix;
5. identical declared type — a metadata-only restatement;
6. coercion classification via `lookup_coercion` (T1/T2/T3), with any
   unproven pair falling back to `type.assignment_cast_unknown.no_using`
   rather than being silently assumed binary-coercible.

None of these branches report `unsupported_evidence`: that status is reserved
for missing required catalog evidence, and an unproven cast path is a fact
this engine can act on conservatively.
"""

from __future__ import annotations

from dataclasses import dataclass

from pginspect.impact.models.card import ImpactConfidence
from pginspect.impact.models.catalog_types import PgCastRow
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ConfidenceLevel,
    ExecutionPrediction,
    ImpactScaleConfidence,
    LockMode,
    PhysicalTriState,
)
from pginspect.impact.rules.coercion import lookup_coercion
from pginspect.impact.rules.contracts import AUTHORIZATION_LIMITATION, RuleVerdict
from pginspect.impact.rules.severity import apply_physical_invariants, derive_risk

RULE_ASSIGNMENT_CAST_UNKNOWN = "type.assignment_cast_unknown.no_using"
RULE_COLLATION_CHANGE = "type.collation_change.conservative_may_fail"
RULE_DOMAIN_BOUNDARY = "type.domain_boundary.conservative_may_fail"
RULE_NO_ASSIGNMENT_CAST = "type.no_assignment_cast.no_using"
RULE_OPAQUE_USING = "type.opaque_using"
RULE_PROVEN_REWRITE = "type.proven_rewrite"
RULE_SAME_DECLARED_TYPE = "type.same_declared_type.no_using"
RULE_TYPMOD_CHANGE = "type.typmod_change.conservative_may_fail"

__all__ = [
    "RULE_ASSIGNMENT_CAST_UNKNOWN",
    "RULE_COLLATION_CHANGE",
    "RULE_DOMAIN_BOUNDARY",
    "RULE_NO_ASSIGNMENT_CAST",
    "RULE_OPAQUE_USING",
    "RULE_PROVEN_REWRITE",
    "RULE_SAME_DECLARED_TYPE",
    "RULE_TYPMOD_CHANGE",
    "TypeChangeFacts",
    "binary_rule_key",
    "evaluate_type_change",
]

_YES = PhysicalTriState.YES
_NO = PhysicalTriState.NO
_POSSIBLE = PhysicalTriState.POSSIBLE
_NOT_APPLICABLE = PhysicalTriState.NOT_APPLICABLE

#: Last major on which a binary-coercible type change still rewrote btree
#: indexes on the column (design section 3.6, T2 per-major subtable).
BINARY_INDEX_REBUILD_LAST_MAJOR = 14


@dataclass(frozen=True)
class TypeChangeFacts:
    """Every axis design section 3.6 branches on, already resolved.

    `source_typmod` / `target_typmod` use PostgreSQL's own encoding, where
    ``-1`` means "no modifier". `source_collation_oid` /
    `target_collation_oid` are `None` for a non-collatable type, which is why
    a collatable/non-collatable pair (e.g. ``integer -> text``) is not read as
    a collation change.

    `using_identity_proven` is normally `False`: proving that a ``USING``
    expression is the identity on the column requires evidence the MVP does
    not collect, and an unproven expression is treated as opaque.
    """

    server_major: int
    source_type_name: str
    target_type_name: str
    source_typmod: int = -1
    target_typmod: int = -1
    source_collation_oid: int | None = None
    target_collation_oid: int | None = None
    source_is_domain: bool = False
    target_is_domain: bool = False
    using_present: bool = False
    using_identity_proven: bool = False
    affected_indexes_exist: bool = False
    index_names: tuple[str, ...] = ()
    metrics_present: bool = True
    pg_cast_rows: tuple[PgCastRow, ...] = ()
    table_exists: bool = True


def binary_rule_key(source_type_name: str, target_type_name: str) -> str:
    """Rule key for a proven binary-coercible pair (design section 3.6, T2).

    The qualifiers are part of the key because the binary verdict is only
    valid under them: they are checked before this branch is reached.
    """
    source = _normalize(source_type_name)
    target = _normalize(target_type_name)
    return f"type.binary.{source}_to_{target}.same_collation.no_domain.no_using"


def evaluate_type_change(facts: TypeChangeFacts) -> RuleVerdict:
    """Return the single allowed verdict for one ``ALTER COLUMN ... TYPE``."""
    source = _normalize(facts.source_type_name)
    target = _normalize(facts.target_type_name)

    if facts.using_present and not facts.using_identity_proven:
        return _conservative(
            RULE_OPAQUE_USING,
            facts,
            why=("USING expression is not proven to be the identity on the column",),
        )

    if facts.source_is_domain != facts.target_is_domain:
        return _conservative(
            RULE_DOMAIN_BOUNDARY,
            facts,
            why=("change crosses a domain boundary, so domain constraints are re-checked",),
        )

    if _collation_changed(facts):
        return _conservative(
            RULE_COLLATION_CHANGE,
            facts,
            why=("column collation changes, so collation-dependent order is not preserved",),
        )

    if facts.source_typmod != facts.target_typmod:
        return _conservative(
            RULE_TYPMOD_CHANGE,
            facts,
            why=("type modifier changes; neither widening nor narrowing is assumed safe",),
        )

    if source == target:
        return _build(
            rule_key=RULE_SAME_DECLARED_TYPE,
            facts=facts,
            execution_prediction=ExecutionPrediction.APPLIES,
            rewrite=_NO,
            scan=_NO,
            index_rebuild=_NO,
            why=("declared type, modifier, and collation are unchanged",),
        )

    coercion = lookup_coercion(
        source,
        target,
        context="assignment",
        pg_cast_rows=facts.pg_cast_rows,
    )

    if coercion.status == "found" and coercion.method == "binary":
        return _build(
            rule_key=binary_rule_key(source, target),
            facts=facts,
            execution_prediction=ExecutionPrediction.APPLIES,
            rewrite=_NO,
            scan=_NO,
            index_rebuild=_binary_index_rebuild(facts),
            coercion_evidence_id=coercion.evidence_id,
            why=(f"{source} -> {target} is binary-coercible, so stored values are unchanged",),
        )

    if coercion.status == "found":
        return _build(
            rule_key=RULE_PROVEN_REWRITE,
            facts=facts,
            execution_prediction=ExecutionPrediction.APPLIES,
            rewrite=_YES,
            scan=_YES,
            index_rebuild=_indexed(facts, _YES),
            coercion_evidence_id=coercion.evidence_id,
            why=(
                f"{source} -> {target} has a proven non-binary coercion, so every row is rewritten",
            ),
        )

    if coercion.status == "checked_in_absence":
        return _build(
            rule_key=coercion.rule_key or RULE_NO_ASSIGNMENT_CAST,
            facts=facts,
            execution_prediction=ExecutionPrediction.WOULD_FAIL,
            rewrite=_NOT_APPLICABLE,
            scan=_NOT_APPLICABLE,
            index_rebuild=_NOT_APPLICABLE,
            coercion_evidence_id=coercion.evidence_id,
            why=(f"no assignment cast exists for {source} -> {target} and no USING was given",),
        )

    return _conservative(
        RULE_ASSIGNMENT_CAST_UNKNOWN,
        facts,
        why=(f"no proven coercion path for {source} -> {target}",),
    )


def _normalize(type_name: str) -> str:
    return type_name.strip().lower()


def _collation_changed(facts: TypeChangeFacts) -> bool:
    """True only when both sides are collatable and the collation differs.

    A pair where one side is not collatable (`None`) is a type change, not a
    collation change, and is classified by the branches that follow.
    """
    if facts.source_collation_oid is None or facts.target_collation_oid is None:
        return False
    return facts.source_collation_oid != facts.target_collation_oid


def _indexed(facts: TypeChangeFacts, present: PhysicalTriState) -> PhysicalTriState:
    return present if facts.affected_indexes_exist else _NO


def _binary_index_rebuild(facts: TypeChangeFacts) -> PhysicalTriState:
    if not facts.affected_indexes_exist:
        return _NO
    if facts.server_major <= BINARY_INDEX_REBUILD_LAST_MAJOR:
        return _YES
    return _NO


def _confidence(*, metrics_present: bool) -> ImpactConfidence:
    return ImpactConfidence(
        lock=ConfidenceLevel.HIGH,
        rewrite=ConfidenceLevel.HIGH,
        execution=ConfidenceLevel.HIGH,
        dependencies=ConfidenceLevel.HIGH,
        impact_scale=(
            ImpactScaleConfidence.MEDIUM if metrics_present else ImpactScaleConfidence.LOW
        ),
    )


def _conservative(
    rule_key: str,
    facts: TypeChangeFacts,
    *,
    why: tuple[str, ...],
) -> RuleVerdict:
    return _build(
        rule_key=rule_key,
        facts=facts,
        execution_prediction=ExecutionPrediction.MAY_FAIL,
        rewrite=_POSSIBLE,
        scan=_POSSIBLE,
        index_rebuild=_indexed(facts, _POSSIBLE),
        why=why,
    )


def _build(
    *,
    rule_key: str,
    facts: TypeChangeFacts,
    execution_prediction: ExecutionPrediction,
    rewrite: PhysicalTriState,
    scan: PhysicalTriState,
    index_rebuild: PhysicalTriState,
    why: tuple[str, ...],
    coercion_evidence_id: str | None = None,
) -> RuleVerdict:
    rewrite, scan, index_rebuild = apply_physical_invariants(rewrite, scan, index_rebuild)
    lock = LockMode.ACCESS_EXCLUSIVE_LOCK if facts.table_exists else LockMode.NOT_APPLICABLE
    risk = derive_risk(
        execution_prediction=execution_prediction,
        lock=lock,
        table_rewrite=rewrite,
        table_scan=scan,
        index_rebuild=index_rebuild,
        analysis_status=AnalysisStatus.ANALYZED,
    )
    evidence_ids = [f"rule:{rule_key}"]
    if coercion_evidence_id is not None and coercion_evidence_id not in evidence_ids:
        evidence_ids.append(coercion_evidence_id)
    if index_rebuild in (_YES, _POSSIBLE) or facts.affected_indexes_exist:
        evidence_ids.extend(f"index:{name}" for name in facts.index_names)
    return RuleVerdict(
        rule_key=rule_key,
        analysis_status=AnalysisStatus.ANALYZED,
        execution_prediction=execution_prediction,
        risk=risk,
        lock=lock,
        table_rewrite=rewrite,
        table_scan=scan,
        index_rebuild=index_rebuild,
        confidence=_confidence(metrics_present=facts.metrics_present),
        limitations=(AUTHORIZATION_LIMITATION,),
        evidence_ids=tuple(evidence_ids),
        why=why,
    )
