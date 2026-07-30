"""DROP COLUMN rule engine (plan Task 9, design section 3.8).

`ALTER TABLE ... DROP COLUMN` never touches heap tuples: PostgreSQL marks the
attribute dropped in `pg_attribute` and leaves existing rows alone. The
physical axes are therefore pinned for every outcome of this family
(`rewrite=no`, `scan=no`, `index_rebuild=no`, design section 3.2), and the
only thing the rule has to decide is what the *dependency* evidence proves:
whether the statement applies, fails, or cannot be judged at all.

Dependency edges arrive already bucketed by the catalog layer (design
section 2.8); this module never re-derives a bucket from `deptype`:

- `internal` / `automatic` — objects the server drops together with the
  column (indexes, defaults, constraint-backed artifacts). They never block.
- `external_blocking` — an independent object (a view, a foreign key from
  another table, ...) that makes the server refuse a RESTRICT drop.
- `cascade` — an object the server will drop as a consequence of the drop.

Evidence honesty (design sections 2.9 / 3.3): the "no external blockers"
claim is only possible over a complete, untruncated dependency graph and a
resolved target column. When any of that is missing the verdict is
`unsupported_evidence` / `not_evaluated` / `not_applicable`, which
`aggregate_exit_code` reports as exit 3 rather than a possibly understated
`applies`.

This module holds no catalog access and no SQL: it maps facts to a verdict.
Object-level dependency evidence ids (`dep:view:...`) are attached later, at
`ImpactStatementCard` assembly, where dependent objects have names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pginspect.impact.models.card import ImpactConfidence
from pginspect.impact.models.catalog_types import DependencyBucket, DependencyEdge
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

DROP_COLUMN_DEPENDENCY_LIMITATION = (
    "Only catalog-proven dependencies are detected; textual or dynamically built "
    "references to the column are undetectable."
)
DROP_COLUMN_INCOMPLETE_EVIDENCE_LIMITATION = (
    "Dependency evidence for the target column is incomplete; no execution, "
    "dependency, or risk claim is made for this statement."
)
DROP_COLUMN_METRICS_LIMITATION = (
    "Relation metrics were not observed; impact scale is not estimated."
)

RULE_KEY_NO_DEPENDENTS = "drop.no_dependents"
RULE_KEY_INTERNAL_ONLY = "drop.internal_only"
RULE_KEY_AUTOMATIC_ONLY = "drop.automatic_only"
RULE_KEY_EXTERNAL_BLOCKER_RESTRICT = "drop.external_blocker_restrict"
RULE_KEY_CASCADE_EXTERNAL = "drop.cascade_external"
RULE_KEY_UNSUPPORTED_EVIDENCE = "drop.unsupported_evidence"

__all__ = [
    "DROP_COLUMN_DEPENDENCY_LIMITATION",
    "DROP_COLUMN_INCOMPLETE_EVIDENCE_LIMITATION",
    "DROP_COLUMN_METRICS_LIMITATION",
    "RULE_KEY_AUTOMATIC_ONLY",
    "RULE_KEY_CASCADE_EXTERNAL",
    "RULE_KEY_EXTERNAL_BLOCKER_RESTRICT",
    "RULE_KEY_INTERNAL_ONLY",
    "RULE_KEY_NO_DEPENDENTS",
    "RULE_KEY_UNSUPPORTED_EVIDENCE",
    "DropColumnFacts",
    "evaluate_drop_column",
]


@dataclass(frozen=True)
class DropColumnFacts:
    """Everything the DROP COLUMN rule is allowed to look at.

    `effective_behavior` is the parser's resolved behavior (design section
    1b family 3): a written `RESTRICT` and an omitted behavior both arrive
    as `"restrict"`.

    `dependency_edges` are the bucketed edges reaching the target column,
    and `dependency_graph_complete` / `truncated_at_limit` describe the BFS
    that produced them (design section 2.8). `required_evidence_missing` is
    the caller's escape hatch for any other required DROP evidence that
    could not be read (design section 2.9).

    `metrics_present` is optional evidence: it moves `impact_scale`
    confidence only and never changes a semantic verdict (design section
    3.4).
    """

    table_exists: bool
    column_exists: bool
    effective_behavior: Literal["restrict", "cascade"]
    dependency_edges: tuple[DependencyEdge, ...] = ()
    dependency_graph_complete: bool = True
    truncated_at_limit: bool = False
    required_evidence_missing: bool = False
    metrics_present: bool = False


def evaluate_drop_column(facts: DropColumnFacts) -> RuleVerdict:
    """Score one `ALTER TABLE ... DROP COLUMN` against design section 3.8.

    Evidence completeness is checked first: an incomplete or truncated
    dependency graph, or an unresolved target, yields `unsupported_evidence`
    and never `applies` / `would_fail`. Otherwise the bucketed edges decide:

    | Buckets present | Behavior | Execution | Risk |
    |---|---|---|---|
    | none / internal / automatic | any | `applies` | `warning` |
    | `external_blocking` | `restrict` | `would_fail` | `critical` |
    | `external_blocking` | `cascade` | `applies` | `critical` |
    | `cascade` | any | `applies` | `critical` |

    A `cascade`-bucketed edge is treated as a cascade consequence whatever
    the written behavior, because bucketing is the catalog layer's decision:
    an edge that would block is bucketed `external_blocking` instead.
    """
    missing_evidence = _missing_required_evidence(facts)
    if missing_evidence is not None:
        return _unsupported_verdict(facts, detail=missing_evidence)

    buckets = frozenset(edge.bucket for edge in facts.dependency_edges)

    if "external_blocking" in buckets and facts.effective_behavior == "restrict":
        blockers = _count(facts, "external_blocking")
        return _analyzed_verdict(
            facts,
            rule_key=RULE_KEY_EXTERNAL_BLOCKER_RESTRICT,
            execution_prediction=ExecutionPrediction.WOULD_FAIL,
            cascade_dependents=False,
            why=(
                f"{blockers} catalog-proven external dependent object(s) block the drop "
                f"under RESTRICT (written or default) behavior.",
            ),
        )

    if buckets & {"external_blocking", "cascade"}:
        dropped = _count(facts, "external_blocking") + _count(facts, "cascade")
        return _analyzed_verdict(
            facts,
            rule_key=RULE_KEY_CASCADE_EXTERNAL,
            execution_prediction=ExecutionPrediction.APPLIES,
            cascade_dependents=True,
            why=(
                f"CASCADE drops {dropped} catalog-proven dependent object(s) "
                f"beyond the target column.",
            ),
        )

    if not buckets:
        return _analyzed_verdict(
            facts,
            rule_key=RULE_KEY_NO_DEPENDENTS,
            execution_prediction=ExecutionPrediction.APPLIES,
            cascade_dependents=False,
            why=("No catalog-proven dependent objects reference the target column.",),
        )

    kept = _count(facts, "internal") + _count(facts, "automatic")
    rule_key = RULE_KEY_INTERNAL_ONLY if "internal" in buckets else RULE_KEY_AUTOMATIC_ONLY
    return _analyzed_verdict(
        facts,
        rule_key=rule_key,
        execution_prediction=ExecutionPrediction.APPLIES,
        cascade_dependents=False,
        why=(
            f"{kept} dependent object(s) are internal or automatic and are dropped "
            f"together with the column; no external dependent blocks the drop.",
        ),
    )


def _missing_required_evidence(facts: DropColumnFacts) -> str | None:
    """Name the first required DROP evidence that is unavailable, if any."""
    if not facts.table_exists:
        return "no relation snapshot for the target table"
    if not facts.column_exists:
        return "no column snapshot for the target column"
    if facts.required_evidence_missing:
        return "required catalog evidence for the drop is missing"
    if facts.truncated_at_limit:
        return "dependency traversal stopped at the edge limit"
    if not facts.dependency_graph_complete:
        return "dependency graph is incomplete"
    return None


def _count(facts: DropColumnFacts, bucket: DependencyBucket) -> int:
    return sum(1 for edge in facts.dependency_edges if edge.bucket == bucket)


def _analyzed_verdict(
    facts: DropColumnFacts,
    *,
    rule_key: str,
    execution_prediction: ExecutionPrediction,
    cascade_dependents: bool,
    why: tuple[str, ...],
) -> RuleVerdict:
    rewrite, scan, index_rebuild = apply_physical_invariants(
        PhysicalTriState.NO, PhysicalTriState.NO, PhysicalTriState.NO
    )
    lock = LockMode.ACCESS_EXCLUSIVE_LOCK
    risk = derive_risk(
        execution_prediction=execution_prediction,
        lock=lock,
        table_rewrite=rewrite,
        table_scan=scan,
        index_rebuild=index_rebuild,
        analysis_status=AnalysisStatus.ANALYZED,
        cascade_dependents=cascade_dependents,
    )
    limitations = [DROP_COLUMN_DEPENDENCY_LIMITATION, AUTHORIZATION_LIMITATION]
    if not facts.metrics_present:
        limitations.append(DROP_COLUMN_METRICS_LIMITATION)
    return RuleVerdict(
        rule_key=rule_key,
        analysis_status=AnalysisStatus.ANALYZED,
        execution_prediction=execution_prediction,
        risk=risk,
        lock=lock,
        table_rewrite=rewrite,
        table_scan=scan,
        index_rebuild=index_rebuild,
        confidence=ImpactConfidence(
            lock=ConfidenceLevel.HIGH,
            rewrite=ConfidenceLevel.HIGH,
            execution=ConfidenceLevel.HIGH,
            dependencies=ConfidenceLevel.HIGH,
            impact_scale=(
                ImpactScaleConfidence.MEDIUM
                if facts.metrics_present
                else ImpactScaleConfidence.UNKNOWN
            ),
        ),
        limitations=tuple(limitations),
        evidence_ids=(f"rule:{rule_key}",),
        why=why,
    )


def _unsupported_verdict(facts: DropColumnFacts, *, detail: str) -> RuleVerdict:
    """Report incompleteness without claiming an execution outcome.

    The physical axes stay `no` because they follow from the statement form
    alone (design section 3.2), but `lock` is only claimed when the target
    column was actually resolved. `derive_risk` collapses any non-`analyzed`
    status to `not_applicable`, so the pinned axes cannot leak into a risk
    claim. The authorization and catalog-proven-dependency limitations are
    deliberately omitted: both qualify an analysis that did not happen.
    """
    target_resolved = facts.table_exists and facts.column_exists
    rewrite, scan, index_rebuild = apply_physical_invariants(
        PhysicalTriState.NO, PhysicalTriState.NO, PhysicalTriState.NO
    )
    lock = LockMode.ACCESS_EXCLUSIVE_LOCK if target_resolved else LockMode.UNKNOWN
    return RuleVerdict(
        rule_key=RULE_KEY_UNSUPPORTED_EVIDENCE,
        analysis_status=AnalysisStatus.UNSUPPORTED_EVIDENCE,
        execution_prediction=ExecutionPrediction.NOT_EVALUATED,
        risk=derive_risk(
            execution_prediction=ExecutionPrediction.NOT_EVALUATED,
            lock=lock,
            table_rewrite=rewrite,
            table_scan=scan,
            index_rebuild=index_rebuild,
            analysis_status=AnalysisStatus.UNSUPPORTED_EVIDENCE,
        ),
        lock=lock,
        table_rewrite=rewrite,
        table_scan=scan,
        index_rebuild=index_rebuild,
        confidence=ImpactConfidence(
            lock=ConfidenceLevel.HIGH if target_resolved else ConfidenceLevel.NOT_APPLICABLE,
            rewrite=ConfidenceLevel.HIGH,
            execution=ConfidenceLevel.NOT_APPLICABLE,
            dependencies=ConfidenceLevel.NOT_APPLICABLE,
            impact_scale=ImpactScaleConfidence.NOT_APPLICABLE,
        ),
        limitations=(DROP_COLUMN_INCOMPLETE_EVIDENCE_LIMITATION,),
        evidence_ids=(f"rule:{RULE_KEY_UNSUPPORTED_EVIDENCE}",),
        why=(f"Analysis skipped: {detail}.",),
    )
