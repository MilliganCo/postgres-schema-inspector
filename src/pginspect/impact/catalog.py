"""Catalog gatherers building `CatalogSnapshot` from `QueryExecutor` rows.

Every read here goes through the abstract `QueryExecutor` protocol
(`query_exec.py`); this module never imports psycopg, never holds a
connection/cursor, and never calls a `pg_*_is_visible` helper. Dependency
traversal is a bounded BFS (design section 2.8): once `max_edges` total
edges have been collected, traversal stops and the caller must report
`dependency_graph_complete=false`, `truncated_at_limit=true`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from pginspect.impact.models.catalog_types import (
    ColumnSnapshot,
    ConstraintSnapshot,
    DependencyEdge,
    DomainConstraintSnapshot,
    FunctionSnapshot,
    IndexSnapshot,
    MetricObservation,
    PgCastRow,
    RelationMetrics,
    RelationSnapshot,
    TypeSnapshot,
)
from pginspect.impact.query_exec import QueryExecutor

MAX_DEPENDENCY_EDGES = 10_000

__all__ = [
    "MAX_DEPENDENCY_EDGES",
    "fetch_relation_snapshot",
    "fetch_type_snapshot",
    "fetch_function_snapshot",
    "fetch_relation_metrics",
    "fetch_pg_cast_rows",
    "gather_dependency_edges",
    "build_metric_observation",
]

_INTERNAL_DEPTYPE = "i"
_AUTOMATIC_DEPTYPE = "a"

# `pg_depend.classid`/`refclassid` values for the object kinds this package
# cares about (design section 2.8 dependency bucket classification is
# deliberately conservative here; DROP-behavior-aware reclassification is a
# Task 9 concern).
_RELATION_CLASS_KIND = "relation"
_UNKNOWN_CLASS_KIND = "unknown"


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        raise TypeError("expected int, got bool")
    if not isinstance(value, (int, str, float)):
        raise TypeError(f"cannot coerce {value!r} to int")
    return int(value)


def _as_optional_int(value: object) -> int | None:
    return None if value is None else _as_int(value)


def _as_str(value: object) -> str:
    return str(value)


def _as_optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _as_bool(value: object) -> bool:
    return bool(value)


def _as_int_tuple(value: object) -> tuple[int, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(_as_int(item) for item in value)
    return ()


def _row_to_column(row: Mapping[str, object]) -> ColumnSnapshot:
    return ColumnSnapshot(
        attnum=_as_int(row["attnum"]),
        attname=_as_str(row["attname"]),
        type_oid=_as_int(row["type_oid"]),
        typmod=_as_int(row["typmod"]),
        attndims=_as_int(row["attndims"]),
        attnotnull=_as_bool(row["attnotnull"]),
        attisdropped=_as_bool(row["attisdropped"]),
        identity=_as_str(row["identity"]),  # type: ignore[arg-type]
        generated=_as_str(row["generated"]),  # type: ignore[arg-type]
        default_bin=_as_optional_str(row["default_bin"]),
        collation_oid=_as_optional_int(row["collation_oid"]),
    )


def _row_to_index(row: Mapping[str, object]) -> IndexSnapshot:
    return IndexSnapshot(
        oid=_as_int(row["oid"]),
        nspname=_as_str(row["nspname"]),
        relname=_as_str(row["relname"]),
        indrelid=_as_int(row["indrelid"]),
        indisunique=_as_bool(row["indisunique"]),
        indisprimary=_as_bool(row["indisprimary"]),
        indisexclusion=_as_bool(row["indisexclusion"]),
        indkey_attnums=_as_int_tuple(row["indkey_attnums"]),
        indisvalid=_as_bool(row["indisvalid"]),
        predicate_present=_as_bool(row["predicate_present"]),
        is_constraint_backed=_as_bool(row["is_constraint_backed"]),
    )


def _row_to_constraint(row: Mapping[str, object]) -> ConstraintSnapshot:
    return ConstraintSnapshot(
        oid=_as_int(row["oid"]),
        conname=_as_str(row["conname"]),
        contype=_as_str(row["contype"]),
        conrelid=_as_int(row["conrelid"]),
        confrelid=_as_int(row["confrelid"]),
        conkey_attnums=_as_int_tuple(row["conkey_attnums"]),
        confkey_attnums=_as_int_tuple(row["confkey_attnums"]),
        confupdtype=_as_str(row["confupdtype"]),
        confdeltype=_as_str(row["confdeltype"]),
    )


def _row_to_domain_constraint(row: Mapping[str, object]) -> DomainConstraintSnapshot:
    return DomainConstraintSnapshot(
        oid=_as_int(row["oid"]),
        conname=_as_str(row["conname"]),
        contype=_as_str(row["contype"]),
        conbin_present=_as_bool(row["conbin_present"]),
    )


def fetch_relation_snapshot(executor: QueryExecutor, oid: int) -> RelationSnapshot | None:
    """Gather one `RelationSnapshot` (core row + columns + indexes + constraints).

    Returns `None` when the relation oid no longer resolves to a row
    (caller decides whether that is `unsupported_evidence` or a
    deterministic missing-target outcome).
    """
    core = executor.fetch_one("impact.fetch_relation", (oid,))
    if core is None:
        return None

    columns = tuple(
        _row_to_column(row) for row in executor.fetch_all("impact.fetch_columns", (oid,))
    )
    indexes = tuple(
        _row_to_index(row) for row in executor.fetch_all("impact.fetch_indexes", (oid,))
    )
    constraints = tuple(
        _row_to_constraint(row) for row in executor.fetch_all("impact.fetch_constraints", (oid,))
    )

    return RelationSnapshot(
        oid=_as_int(core["oid"]),
        nspname=_as_str(core["nspname"]),
        relname=_as_str(core["relname"]),
        relkind=_as_str(core["relkind"]),
        relpersistence=_as_str(core["relpersistence"]),
        relispartition=_as_bool(core["relispartition"]),
        inherits_parents=_as_int_tuple(core["inherits_parents"]),
        inherits_children=_as_int_tuple(core["inherits_children"]),
        columns=columns,
        indexes=indexes,
        constraints=constraints,
    )


def fetch_type_snapshot(executor: QueryExecutor, oid: int) -> TypeSnapshot | None:
    """Gather one `TypeSnapshot`, including domain constraints when `typtype=d`."""
    core = executor.fetch_one("impact.fetch_type", (oid,))
    if core is None:
        return None

    domain_constraints = tuple(
        _row_to_domain_constraint(row)
        for row in executor.fetch_all("impact.fetch_domain_constraints", (oid,))
    )

    return TypeSnapshot(
        oid=_as_int(core["oid"]),
        nspname=_as_str(core["nspname"]),
        typname=_as_str(core["typname"]),
        typtype=_as_str(core["typtype"]),
        typcategory=_as_str(core["typcategory"]),
        typbasetype=_as_int(core["typbasetype"]),
        typelem=_as_int(core["typelem"]),
        typarray=_as_int(core["typarray"]),
        typndims=_as_int(core["typndims"]),
        typtypmod=_as_int(core["typtypmod"]),
        typlen=_as_int(core["typlen"]),
        typbyval=_as_bool(core["typbyval"]),
        typalign=_as_str(core["typalign"]),
        typcollation=_as_int(core["typcollation"]),
        typdefaultbin=_as_optional_str(core["typdefaultbin"]),
        typdefault=_as_optional_str(core["typdefault"]),
        domain_not_null=_as_bool(core["domain_not_null"]),
        domain_constraints=domain_constraints,
    )


def fetch_function_snapshot(executor: QueryExecutor, oid: int) -> FunctionSnapshot | None:
    row = executor.fetch_one("impact.fetch_function", (oid,))
    if row is None:
        return None
    return FunctionSnapshot(
        oid=_as_int(row["oid"]),
        nspname=_as_str(row["nspname"]),
        proname=_as_str(row["proname"]),
        proargtypes=_as_int_tuple(row["proargtypes"]),
        prorettype=_as_int(row["prorettype"]),
        provolatile=_as_str(row["provolatile"]),  # type: ignore[arg-type]
        prokind=_as_str(row["prokind"]),
    )


def fetch_relation_metrics(executor: QueryExecutor, oid: int) -> RelationMetrics | None:
    row = executor.fetch_one("impact.fetch_relation_metrics", (oid,))
    if row is None:
        return None
    n_live_tup = row["n_live_tup"]
    return RelationMetrics(
        pg_relation_size=_as_int(row["pg_relation_size"]),
        pg_total_relation_size=_as_int(row["pg_total_relation_size"]),
        indexes_size=_as_int(row["indexes_size"]),
        n_live_tup=None if n_live_tup is None else _as_int(n_live_tup),
        stats_freshness="estimated",
    )


def fetch_pg_cast_rows(
    executor: QueryExecutor, source_oid: int, target_oid: int
) -> tuple[PgCastRow, ...]:
    rows = executor.fetch_all("impact.fetch_pg_cast", (source_oid, target_oid))
    return tuple(
        PgCastRow(
            castsource=_as_int(row["castsource"]),
            casttarget=_as_int(row["casttarget"]),
            castfunc=_as_int(row["castfunc"]),
            castcontext=_as_str(row["castcontext"]),  # type: ignore[arg-type]
            castmethod=_as_str(row["castmethod"]),  # type: ignore[arg-type]
        )
        for row in rows
    )


def _row_to_dependency_edge(row: Mapping[str, object]) -> DependencyEdge:
    deptype = _as_str(row["deptype"])
    if deptype == _INTERNAL_DEPTYPE:
        bucket = "internal"
    elif deptype == _AUTOMATIC_DEPTYPE:
        bucket = "automatic"
    else:
        # Normal ('n') and any other deptype: conservatively "blocks unless
        # CASCADE". Whether a given DROP statement actually cascades this
        # edge is decided by the DROP rule engine (Task 9), not here.
        bucket = "external_blocking"
    return DependencyEdge(
        classid=_as_int(row["classid"]),
        objid=_as_int(row["objid"]),
        objsubid=_as_int(row["objsubid"]),
        refclassid=_as_int(row["refclassid"]),
        refobjid=_as_int(row["refobjid"]),
        refobjsubid=_as_int(row["refobjsubid"]),
        deptype=deptype,
        class_kind=_UNKNOWN_CLASS_KIND,
        ref_class_kind=_RELATION_CLASS_KIND,
        bucket=bucket,  # type: ignore[arg-type]
    )


def gather_dependency_edges(
    executor: QueryExecutor,
    *,
    roots: Sequence[tuple[int, int, int]],
    max_edges: int = MAX_DEPENDENCY_EDGES,
) -> tuple[tuple[DependencyEdge, ...], bool]:
    """Bounded BFS over `pg_depend` edges from the given object-address roots.

    `roots` are `(refclassid, refobjid, refobjsubid)` addresses (e.g. the
    target table/column of a DROP COLUMN). Returns `(edges, truncated)`:
    once `max_edges` total edges have been collected, traversal stops
    immediately rather than continuing past the bound (design section 2.8;
    `truncated=True` maps to `dependency_graph_complete=false`,
    `truncated_at_limit=true`).
    """
    edges: list[DependencyEdge] = []
    visited: set[tuple[int, int, int]] = set()
    queue: deque[tuple[int, int, int]] = deque(roots)
    truncated = False

    while queue:
        target = queue.popleft()
        if target in visited:
            continue
        visited.add(target)

        refclassid, refobjid, refobjsubid = target
        rows = executor.fetch_all(
            "impact.fetch_dependency_edges",
            (refclassid, refobjid, refobjsubid, max_edges + 1),
        )
        for row in rows:
            if len(edges) >= max_edges:
                truncated = True
                break
            edge = _row_to_dependency_edge(row)
            edges.append(edge)
            next_target = (edge.classid, edge.objid, edge.objsubid)
            if next_target not in visited:
                queue.append(next_target)
        if truncated:
            break

    return tuple(edges), truncated


def build_metric_observation(
    relation_metrics: Mapping[int, RelationMetrics],
    *,
    metrics_observed_at: datetime | None = None,
) -> MetricObservation:
    """Assemble a `MetricObservation`, stamping best-effort observation time."""
    observed_at = metrics_observed_at if metrics_observed_at is not None else datetime.now(UTC)
    return MetricObservation(
        metrics_observed_at=observed_at,
        metrics_consistency="best_effort",
        relation_metrics=relation_metrics,
    )
