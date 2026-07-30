"""Factories for DROP COLUMN rule facts (plan Task 9).

The oids are arbitrary but stable so a failing assertion points at a named
edge rather than at a literal. Every builder defaults to the D1/D2/D3 shape
of design section 5.5: a single table `t` with a target column, and
dependents reaching that column.
"""

from __future__ import annotations

from typing import Literal

from pginspect.impact.models.catalog_types import DependencyBucket, DependencyEdge
from pginspect.impact.rules.drop_column import DropColumnFacts

PG_CLASS_OID = 1259
TARGET_TABLE_OID = 16_400
TARGET_ATTNUM = 2


def dependency_edge(
    bucket: DependencyBucket,
    *,
    objid: int,
    class_kind: str,
    deptype: str,
) -> DependencyEdge:
    """One bucketed edge from a dependent object to the target column."""
    return DependencyEdge(
        classid=PG_CLASS_OID,
        objid=objid,
        objsubid=0,
        refclassid=PG_CLASS_OID,
        refobjid=TARGET_TABLE_OID,
        refobjsubid=TARGET_ATTNUM,
        deptype=deptype,
        class_kind=class_kind,
        ref_class_kind="table",
        bucket=bucket,
    )


def internal_index_edge(*, objid: int = 16_501) -> DependencyEdge:
    """D1: the index the server drops together with the column."""
    return dependency_edge("internal", objid=objid, class_kind="index", deptype="i")


def automatic_default_edge(*, objid: int = 16_502) -> DependencyEdge:
    """A column default / constraint the server removes with the column."""
    return dependency_edge("automatic", objid=objid, class_kind="constraint", deptype="a")


def external_view_edge(*, objid: int = 16_503) -> DependencyEdge:
    """D2: an independent view that refuses to let RESTRICT through."""
    return dependency_edge("external_blocking", objid=objid, class_kind="view", deptype="n")


def cascade_view_edge(*, objid: int = 16_504) -> DependencyEdge:
    """D3: a dependent the catalog layer already marked as cascade-dropped."""
    return dependency_edge("cascade", objid=objid, class_kind="view", deptype="n")


def drop_facts(
    *,
    edges: tuple[DependencyEdge, ...] = (),
    effective_behavior: Literal["restrict", "cascade"] = "restrict",
    table_exists: bool = True,
    column_exists: bool = True,
    dependency_graph_complete: bool = True,
    truncated_at_limit: bool = False,
    required_evidence_missing: bool = False,
    metrics_present: bool = True,
) -> DropColumnFacts:
    """Complete, analyzable DROP COLUMN facts unless a flag says otherwise."""
    return DropColumnFacts(
        table_exists=table_exists,
        column_exists=column_exists,
        effective_behavior=effective_behavior,
        dependency_edges=edges,
        dependency_graph_complete=dependency_graph_complete,
        truncated_at_limit=truncated_at_limit,
        required_evidence_missing=required_evidence_missing,
        metrics_present=metrics_present,
    )
