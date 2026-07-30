"""ADD COLUMN rule engine — full normative matrix (plan Task 8, design section 3.7).

The engine is deliberately *downstream* of effective-default classification.
Design section 3.7 pins the effective default as

```text
effective_default:
  explicit column DEFAULT expression, if present
  else domain DEFAULT (TypeSnapshot.typdefaultbin / typdefault), if typtype=d and present
  else NULL
```

Deciding which of those three branches applies, and whether the resulting
expression is volatile / coercible / non-null, needs the parsed DEFAULT span,
the target `TypeSnapshot`, and — for the qualified built-in allowlist — a
resolved `FunctionSnapshot`. All of that is the caller's job. `AddColumnFacts`
carries only the already-classified axes, so this module owns exactly one
thing: mapping classified axes onto the normative verdict.

Evaluation order (design section 3.7, precedence is normative because several
predicates can hold at once):

1. `default_coercion=proven_invalid` → `add.coercion_invalid` (the statement
   cannot execute, so no physical work is predicted).
2. `domain_has_constraints` → `add.domain_with_constraints`. Design section 3.7
   states this holds for every major 14-18 "in addition to effective_default
   analysis", and the constrained-domain row is the strictly worse outcome, so
   it is reported ahead of the default-driven rows.
3. Effective default present but not classifiable → `add.effective_default_unknown`.
4. `default_volatility=proven_volatile` → `add.volatile_valid`.
5. `NOT NULL` rows.
6. nullable rows.

`n_live_tup` is carried on the facts and never read: `pg_stat_all_tables`
reports an estimate, so it can neither prove nor disprove emptiness (design
section 3.7, fixtures A4/A5). Keeping the field visible — and unused — is what
makes "A5 has the same verdict as A4" a property of this module rather than of
the caller that happened not to pass the stat.

This module holds pure decision logic: no psycopg import, no SQL text, no
query execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pginspect.impact.models.card import ImpactConfidence
from pginspect.impact.models.catalog_types import (
    DomainConstraintSnapshot,
    FunctionSnapshot,
    TypeSnapshot,
)
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ConfidenceLevel,
    ExecutionPrediction,
    ImpactScaleConfidence,
    LockMode,
    PhysicalTriState,
)
from pginspect.impact.rules.contracts import AUTHORIZATION_LIMITATION, RuleVerdict
from pginspect.impact.rules.severity import apply_physical_invariants, derive_risk

TABLE_EMPTINESS_LIMITATION = (
    "Table emptiness is not proven from catalog evidence (n_live_tup is an estimate)."
)

EffectiveDefaultKind = Literal[
    "null",
    "explicit_null",
    "column_expression",
    "domain_expression",
]
DefaultVolatility = Literal["proven_nonvolatile", "proven_volatile", "unknown"]
DefaultCoercion = Literal["proven_valid", "proven_invalid", "unknown"]
DefaultNullability = Literal["proven_nonnull", "proven_null", "unknown"]

__all__ = [
    "TABLE_EMPTINESS_LIMITATION",
    "AddColumnFacts",
    "DefaultCoercion",
    "DefaultNullability",
    "DefaultVolatility",
    "EffectiveDefaultKind",
    "evaluate_add_column",
]

SUPPORTED_SERVER_MAJORS = frozenset(range(14, 19))

_EFFECTIVE_NULL_KINDS = frozenset({"null", "explicit_null"})

_YES = PhysicalTriState.YES
_NO = PhysicalTriState.NO
_POSSIBLE = PhysicalTriState.POSSIBLE
_NOT_APPLICABLE = PhysicalTriState.NOT_APPLICABLE


@dataclass(frozen=True)
class AddColumnFacts:
    """Classified ADD COLUMN axes for one statement (design section 3.7).

    `effective_default_kind` separates the two ways an effective default can
    be NULL — nothing written and no domain default (`null`, fixture A1)
    versus a written `DEFAULT NULL` (`explicit_null`) — from the two ways it
    can be an expression (`column_expression` / `domain_expression`). Both
    NULL kinds reach the same `add.*.no_default` verdict; the distinction is
    kept because the caller must never collapse "no written column DEFAULT"
    into `no_default` when a domain default exists.

    The trailing catalog fields are evidence carriers only. They never change
    the verdict — `default_volatility` already encodes the outcome of the
    `pg_catalog.now()` vs `pg_catalog.clock_timestamp()` allowlist lookup —
    but they let the assembled card cite the function, domain, and indexes
    that justify it.
    """

    server_major: int
    nullable: bool
    indexes_exist: bool
    metrics_present: bool
    n_live_tup: int | None
    effective_default_kind: EffectiveDefaultKind
    default_volatility: DefaultVolatility
    default_coercion: DefaultCoercion
    default_nullability: DefaultNullability
    domain_has_constraints: bool
    target_type: TypeSnapshot | None = None
    default_function: FunctionSnapshot | None = None
    domain_constraints: tuple[DomainConstraintSnapshot, ...] = ()
    index_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.server_major not in SUPPORTED_SERVER_MAJORS:
            raise ValueError(
                f"unsupported server major for ADD COLUMN analysis: {self.server_major}"
            )


@dataclass(frozen=True)
class _Outcome:
    rule_key: str
    execution: ExecutionPrediction
    rewrite: PhysicalTriState
    scan: PhysicalTriState
    index_rebuild: PhysicalTriState
    why: str


def evaluate_add_column(facts: AddColumnFacts) -> RuleVerdict:
    """Return the normative `RuleVerdict` for one `ADD COLUMN` statement.

    The caller is expected to have resolved the target table, so the lock is
    always `AccessExclusiveLock` (design section 3.6/3.7) and the analysis
    status is always `analyzed` — facts that could not be established are
    reported through the `unknown` axis values, not through this function.
    """
    outcome = _classify(facts)
    rewrite, scan, index_rebuild = apply_physical_invariants(
        outcome.rewrite, outcome.scan, outcome.index_rebuild
    )
    lock = LockMode.ACCESS_EXCLUSIVE_LOCK
    risk = derive_risk(
        execution_prediction=outcome.execution,
        lock=lock,
        table_rewrite=rewrite,
        table_scan=scan,
        index_rebuild=index_rebuild,
        analysis_status=AnalysisStatus.ANALYZED,
    )
    return RuleVerdict(
        rule_key=outcome.rule_key,
        analysis_status=AnalysisStatus.ANALYZED,
        execution_prediction=outcome.execution,
        risk=risk,
        lock=lock,
        table_rewrite=rewrite,
        table_scan=scan,
        index_rebuild=index_rebuild,
        confidence=_confidence(facts),
        limitations=_limitations(facts, outcome.execution),
        evidence_ids=_evidence_ids(facts, outcome.rule_key, index_rebuild),
        why=(outcome.why,),
    )


def _classify(facts: AddColumnFacts) -> _Outcome:
    if facts.default_coercion == "proven_invalid":
        return _Outcome(
            rule_key="add.coercion_invalid",
            execution=ExecutionPrediction.WOULD_FAIL,
            rewrite=_NOT_APPLICABLE,
            scan=_NOT_APPLICABLE,
            index_rebuild=_NOT_APPLICABLE,
            why="The effective DEFAULT cannot be coerced to the new column type.",
        )
    if facts.domain_has_constraints:
        return _Outcome(
            rule_key="add.domain_with_constraints",
            execution=ExecutionPrediction.APPLIES,
            rewrite=_YES,
            scan=_YES,
            index_rebuild=_index_rebuild(facts, _YES),
            why="The new column has a domain type with constraints, which forces a table rewrite.",
        )
    if _has_default_expression(facts) and _is_unclassifiable(facts):
        return _Outcome(
            rule_key="add.effective_default_unknown",
            execution=ExecutionPrediction.MAY_FAIL,
            rewrite=_POSSIBLE,
            scan=_POSSIBLE,
            index_rebuild=_index_rebuild(facts, _POSSIBLE),
            why="The effective DEFAULT is present but not classifiable from catalog evidence.",
        )
    if _has_default_expression(facts) and facts.default_volatility == "proven_volatile":
        return _Outcome(
            rule_key="add.volatile_valid",
            execution=ExecutionPrediction.APPLIES,
            rewrite=_YES,
            scan=_YES,
            index_rebuild=_index_rebuild(facts, _YES),
            why="The effective DEFAULT is volatile, so every existing row gets its own value.",
        )
    if not facts.nullable:
        return _classify_not_null(facts)
    return _classify_nullable(facts)


def _classify_not_null(facts: AddColumnFacts) -> _Outcome:
    if _effective_default_is_null(facts):
        return _Outcome(
            rule_key="add.not_null.no_default",
            execution=ExecutionPrediction.MAY_FAIL,
            rewrite=_NO,
            scan=_POSSIBLE,
            index_rebuild=_NO,
            why="A NOT NULL column without an effective DEFAULT fails if the table holds any row.",
        )
    if facts.default_nullability == "proven_nonnull":
        return _Outcome(
            rule_key="add.not_null.nonvolatile_valid.proven_nonnull",
            execution=ExecutionPrediction.APPLIES,
            rewrite=_NO,
            scan=_NO,
            index_rebuild=_NO,
            why="The effective DEFAULT is non-volatile and proven non-null, satisfying NOT NULL.",
        )
    return _Outcome(
        rule_key="add.not_null.nullability_null_or_unknown",
        execution=ExecutionPrediction.MAY_FAIL,
        rewrite=_NO,
        scan=_POSSIBLE,
        index_rebuild=_NO,
        why="The effective DEFAULT is not proven non-null, so NOT NULL may be violated.",
    )


def _classify_nullable(facts: AddColumnFacts) -> _Outcome:
    if _effective_default_is_null(facts):
        return _Outcome(
            rule_key="add.nullable.no_default",
            execution=ExecutionPrediction.APPLIES,
            rewrite=_NO,
            scan=_NO,
            index_rebuild=_NO,
            why="The effective DEFAULT is NULL, so the new column is catalog-only metadata.",
        )
    return _Outcome(
        rule_key="add.nullable.const_or_nonvolatile_valid",
        execution=ExecutionPrediction.APPLIES,
        rewrite=_NO,
        scan=_NO,
        index_rebuild=_NO,
        why="The effective DEFAULT is constant or non-volatile, so it is stored in the catalog.",
    )


def _effective_default_is_null(facts: AddColumnFacts) -> bool:
    return facts.effective_default_kind in _EFFECTIVE_NULL_KINDS


def _has_default_expression(facts: AddColumnFacts) -> bool:
    return not _effective_default_is_null(facts)


def _is_unclassifiable(facts: AddColumnFacts) -> bool:
    return facts.default_volatility == "unknown" or facts.default_coercion == "unknown"


def _index_rebuild(facts: AddColumnFacts, when_indexes_exist: PhysicalTriState) -> PhysicalTriState:
    """Rewriting rules only touch indexes when the table actually has some."""
    return when_indexes_exist if facts.indexes_exist else _NO


def _confidence(facts: AddColumnFacts) -> ImpactConfidence:
    """Every axis this engine reads is catalog-proven, so the claims are high confidence.

    `impact_scale` is the exception: without `RelationMetrics` there is no
    size evidence at all, and with it the numbers are still estimates.
    """
    return ImpactConfidence(
        lock=ConfidenceLevel.HIGH,
        rewrite=ConfidenceLevel.HIGH,
        execution=ConfidenceLevel.HIGH,
        dependencies=ConfidenceLevel.HIGH,
        impact_scale=(
            ImpactScaleConfidence.MEDIUM if facts.metrics_present else ImpactScaleConfidence.LOW
        ),
    )


def _limitations(facts: AddColumnFacts, execution: ExecutionPrediction) -> tuple[str, ...]:
    """The emptiness limitation is what makes a `NOT NULL` `may_fail` honest.

    It is attached exactly when the prediction hinges on whether rows exist,
    which is the only thing `n_live_tup` could have answered and cannot.
    """
    if not facts.nullable and execution is ExecutionPrediction.MAY_FAIL:
        return (TABLE_EMPTINESS_LIMITATION, AUTHORIZATION_LIMITATION)
    return (AUTHORIZATION_LIMITATION,)


def _evidence_ids(
    facts: AddColumnFacts, rule_key: str, index_rebuild: PhysicalTriState
) -> tuple[str, ...]:
    """Cite the rule, then the catalog objects the caller resolved to reach it.

    Indexes are cited only when they moved `index_rebuild`; on a verdict that
    rebuilds nothing they are not evidence for anything.
    """
    ids = [f"rule:{rule_key}"]
    if facts.target_type is not None:
        ids.append(f"type:{facts.target_type.nspname}.{facts.target_type.typname}")
    if facts.default_function is not None:
        ids.append(f"function:{facts.default_function.nspname}.{facts.default_function.proname}()")
    ids.extend(f"domain_constraint:{constraint.conname}" for constraint in facts.domain_constraints)
    if index_rebuild in (_YES, _POSSIBLE):
        ids.extend(f"index:{name}" for name in facts.index_names)
    return tuple(ids)
