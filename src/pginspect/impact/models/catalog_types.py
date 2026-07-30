"""Catalog evidence structures (design section 2.8).

These are internal analysis structures, not part of the public 0.1 wire
contract (`impact/models/{card,result,evidence}.py`); they are plain frozen
dataclasses, matching the style already used for `ResolutionContext` and
`AnalysisUnit`. This module holds data shapes only — no psycopg import, no
SQL text, no query execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

CoercionContext = Literal["implicit", "assignment", "explicit"]
CoercionMethod = Literal[
    "catalog_function",
    "binary",
    "catalog_inout",
    "automatic_io",
    "domain",
    "array",
    "checked_rule",
]
CoercionOrigin = Literal["pg_cast", "server_generic_rule", "checked_in_rule"]
DependencyBucket = Literal["internal", "automatic", "external_blocking", "cascade"]
StatsFreshness = Literal["unknown", "estimated"]


@dataclass(frozen=True)
class DomainConstraintSnapshot:
    oid: int
    conname: str
    contype: str
    conbin_present: bool


@dataclass(frozen=True)
class ColumnSnapshot:
    attnum: int
    attname: str
    type_oid: int
    typmod: int
    attndims: int
    attnotnull: bool
    attisdropped: bool
    identity: Literal["", "a", "d"]
    generated: Literal["", "s", "v"]
    default_bin: str | None
    collation_oid: int | None


@dataclass(frozen=True)
class IndexSnapshot:
    oid: int
    nspname: str
    relname: str
    indrelid: int
    indisunique: bool
    indisprimary: bool
    indisexclusion: bool
    indkey_attnums: tuple[int, ...]
    indisvalid: bool
    predicate_present: bool
    is_constraint_backed: bool


@dataclass(frozen=True)
class ConstraintSnapshot:
    oid: int
    conname: str
    contype: str
    conrelid: int
    confrelid: int
    conkey_attnums: tuple[int, ...]
    confkey_attnums: tuple[int, ...]
    confupdtype: str
    confdeltype: str


@dataclass(frozen=True)
class RelationSnapshot:
    oid: int
    nspname: str
    relname: str
    relkind: str
    relpersistence: str
    relispartition: bool
    inherits_parents: tuple[int, ...]
    inherits_children: tuple[int, ...]
    columns: tuple[ColumnSnapshot, ...]
    indexes: tuple[IndexSnapshot, ...]
    constraints: tuple[ConstraintSnapshot, ...]


@dataclass(frozen=True)
class TypeSnapshot:
    oid: int
    nspname: str
    typname: str
    typtype: str
    typcategory: str
    typbasetype: int
    typelem: int
    typarray: int
    typndims: int
    typtypmod: int
    typlen: int
    typbyval: bool
    typalign: str
    typcollation: int
    typdefaultbin: str | None
    typdefault: str | None
    domain_not_null: bool
    domain_constraints: tuple[DomainConstraintSnapshot, ...]


@dataclass(frozen=True)
class FunctionSnapshot:
    oid: int
    nspname: str
    proname: str
    proargtypes: tuple[int, ...]
    prorettype: int
    provolatile: Literal["i", "s", "v"]
    prokind: str


@dataclass(frozen=True)
class CoercionEvidence:
    source_oid: int
    target_oid: int
    context: CoercionContext
    method: CoercionMethod
    origin: CoercionOrigin
    evidence_id: str


@dataclass(frozen=True)
class DependencyEdge:
    classid: int
    objid: int
    objsubid: int
    refclassid: int
    refobjid: int
    refobjsubid: int
    deptype: str
    class_kind: str
    ref_class_kind: str
    bucket: DependencyBucket


@dataclass(frozen=True)
class RelationMetrics:
    pg_relation_size: int
    pg_total_relation_size: int
    indexes_size: int
    n_live_tup: int | None
    stats_freshness: StatsFreshness


@dataclass(frozen=True)
class MetricObservation:
    metrics_observed_at: datetime | None
    metrics_consistency: Literal["best_effort"]
    relation_metrics: Mapping[int, RelationMetrics]


@dataclass(frozen=True)
class CatalogSnapshot:
    catalog_snapshot_at: datetime
    server_version_num: int
    relations: Mapping[int, RelationSnapshot]
    types: Mapping[int, TypeSnapshot]
    functions: Mapping[int, FunctionSnapshot]
    coercions: tuple[CoercionEvidence, ...]
    dependency_edges: tuple[DependencyEdge, ...]
    dependency_graph_complete: bool
    truncated_at_limit: bool


@dataclass(frozen=True)
class PgCastRow:
    """Raw `pg_cast` row for one (source, target) type oid pair.

    `castcontext` follows PostgreSQL's own encoding: ``e`` explicit,
    ``a`` assignment, ``i`` implicit. `castmethod`: ``f`` function,
    ``i`` inout, ``b`` binary-coercible.
    """

    castsource: int
    casttarget: int
    castfunc: int
    castcontext: Literal["e", "a", "i"]
    castmethod: Literal["f", "i", "b"]
