"""Name resolution via captured `current_schemas(true)` ranking only.

Design section 2.4: after `search_path` is hardened to `pg_catalog`, the
`pg_*_is_visible` helpers reflect the hardened path and must never be used.
This module instead ranks candidate rows (returned by the allowlisted
`impact.resolve_*` QuerySpecs) against the pre-harden
`ResolutionContext.current_schemas_with_implicit` ordering captured by
`establish_impact_profile`. First match under that ordering wins, mirroring
ordinary unqualified-name lookup semantics.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeVar

from pginspect.impact.preflight import ResolutionContext
from pginspect.impact.query_exec import QueryExecutor
from pginspect.impact.type_names import catalog_typname

ResolutionOutcomeStatus = Literal["resolved", "not_found", "unsupported_resolution"]

__all__ = [
    "ResolutionOutcomeStatus",
    "RelationCandidate",
    "TypeCandidate",
    "FunctionCandidate",
    "RelationResolution",
    "TypeResolution",
    "FunctionResolution",
    "rank_relation_candidates",
    "rank_type_candidates",
    "rank_function_candidates",
    "resolve_relation",
    "resolve_type",
    "resolve_function",
]


@dataclass(frozen=True)
class RelationCandidate:
    oid: int
    nspname: str
    relname: str


@dataclass(frozen=True)
class TypeCandidate:
    oid: int
    nspname: str
    typname: str


@dataclass(frozen=True)
class FunctionCandidate:
    oid: int
    nspname: str
    proname: str


@dataclass(frozen=True)
class RelationResolution:
    status: ResolutionOutcomeStatus
    oid: int | None
    nspname: str | None
    relname: str | None
    detail: str | None


@dataclass(frozen=True)
class TypeResolution:
    status: ResolutionOutcomeStatus
    oid: int | None
    nspname: str | None
    typname: str | None
    detail: str | None


@dataclass(frozen=True)
class FunctionResolution:
    status: ResolutionOutcomeStatus
    oid: int | None
    nspname: str | None
    proname: str | None
    detail: str | None


_CandidateT = TypeVar("_CandidateT", RelationCandidate, TypeCandidate, FunctionCandidate)


def _rank(
    candidates: Sequence[_CandidateT],
    ordering: Sequence[str],
) -> _CandidateT | None:
    """First-match-wins ranking against `current_schemas(true)` ordering.

    Candidates whose schema is absent from `ordering` are never selected.
    """
    ranked: list[tuple[int, _CandidateT]] = []
    for candidate in candidates:
        try:
            rank = ordering.index(candidate.nspname)
        except ValueError:
            continue
        ranked.append((rank, candidate))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]


def rank_relation_candidates(
    candidates: Sequence[RelationCandidate], ordering: Sequence[str]
) -> RelationCandidate | None:
    return _rank(candidates, ordering)


def rank_type_candidates(
    candidates: Sequence[TypeCandidate], ordering: Sequence[str]
) -> TypeCandidate | None:
    return _rank(candidates, ordering)


def rank_function_candidates(
    candidates: Sequence[FunctionCandidate], ordering: Sequence[str]
) -> FunctionCandidate | None:
    return _rank(candidates, ordering)


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str, float)):
        raise TypeError(f"cannot coerce {value!r} to int")
    return int(value)


def _identifier_too_long(name: str, context: ResolutionContext) -> bool:
    """Server truncates identifiers at `max_identifier_length` bytes.

    Design section 2.4: over-long identifiers are `unsupported_resolution`,
    never an invented `would_fail` (the server would silently truncate,
    not error).
    """
    return len(name.encode("utf-8")) >= context.max_identifier_length_bytes


def _relation_rows_to_candidates(
    rows: Sequence[Mapping[str, object]],
) -> tuple[RelationCandidate, ...]:
    return tuple(
        RelationCandidate(
            oid=_as_int(row["oid"]),
            nspname=str(row["nspname"]),
            relname=str(row["relname"]),
        )
        for row in rows
    )


def _type_rows_to_candidates(
    rows: Sequence[Mapping[str, object]],
) -> tuple[TypeCandidate, ...]:
    return tuple(
        TypeCandidate(
            oid=_as_int(row["oid"]),
            nspname=str(row["nspname"]),
            typname=str(row["typname"]),
        )
        for row in rows
    )


def _function_rows_to_candidates(
    rows: Sequence[Mapping[str, object]],
) -> tuple[FunctionCandidate, ...]:
    return tuple(
        FunctionCandidate(
            oid=_as_int(row["oid"]),
            nspname=str(row["nspname"]),
            proname=str(row["proname"]),
        )
        for row in rows
    )


def resolve_relation(
    *,
    schema: str | None,
    name: str,
    context: ResolutionContext,
    executor: QueryExecutor,
) -> RelationResolution:
    """Resolve a (possibly schema-qualified) relation name to at most one oid.

    Qualified names look up the exact schema only (deterministic missing is
    legitimate there). Unqualified names require the winning candidate
    under `current_schemas_with_implicit` to *also* be in the captured
    `current_schema()`; otherwise the result is `unsupported_resolution`
    (never a deterministic "missing" — design section 2.4).
    """
    if _identifier_too_long(name, context):
        return RelationResolution(
            status="unsupported_resolution",
            oid=None,
            nspname=None,
            relname=None,
            detail=f"identifier {name!r} exceeds max_identifier_length_bytes",
        )

    if schema is not None:
        rows = executor.fetch_all("impact.resolve_relation_candidates", ((schema,), name))
        candidates = _relation_rows_to_candidates(rows)
        if not candidates:
            return RelationResolution(
                status="not_found", oid=None, nspname=None, relname=None, detail=None
            )
        chosen = candidates[0]
        return RelationResolution(
            status="resolved",
            oid=chosen.oid,
            nspname=chosen.nspname,
            relname=chosen.relname,
            detail=None,
        )

    if context.current_schema is None:
        return RelationResolution(
            status="unsupported_resolution",
            oid=None,
            nspname=None,
            relname=None,
            detail="current_schema() is NULL; cannot resolve unqualified name",
        )

    rows = executor.fetch_all(
        "impact.resolve_relation_candidates",
        (context.current_schemas_with_implicit, name),
    )
    candidates = _relation_rows_to_candidates(rows)
    winner = rank_relation_candidates(candidates, context.current_schemas_with_implicit)
    if winner is None or winner.nspname != context.current_schema:
        detail = (
            "no candidate found under current_schemas(true)"
            if winner is None
            else (
                f"first match {winner.nspname}.{name} is not in "
                f"current_schema {context.current_schema!r}"
            )
        )
        return RelationResolution(
            status="unsupported_resolution", oid=None, nspname=None, relname=None, detail=detail
        )
    return RelationResolution(
        status="resolved",
        oid=winner.oid,
        nspname=winner.nspname,
        relname=winner.relname,
        detail=None,
    )


def resolve_type(
    *,
    schema: str | None,
    name: str,
    context: ResolutionContext,
    executor: QueryExecutor,
) -> TypeResolution:
    """Resolve a (possibly schema-qualified) type name to at most one oid.

    Unqualified types rank by `current_schemas_with_implicit` only (no
    additional `current_schema()` requirement beyond appearing in the
    ranked path — design section 2.4).
    """
    if _identifier_too_long(name, context):
        return TypeResolution(
            status="unsupported_resolution",
            oid=None,
            nspname=None,
            typname=None,
            detail=f"identifier {name!r} exceeds max_identifier_length_bytes",
        )

    if schema is not None:
        rows = executor.fetch_all(
            "impact.resolve_type_candidates", ((schema,), catalog_typname(name))
        )
        candidates = _type_rows_to_candidates(rows)
        if not candidates:
            return TypeResolution(
                status="not_found", oid=None, nspname=None, typname=None, detail=None
            )
        chosen = candidates[0]
        return TypeResolution(
            status="resolved",
            oid=chosen.oid,
            nspname=chosen.nspname,
            typname=chosen.typname,
            detail=None,
        )

    if context.current_schema is None:
        return TypeResolution(
            status="unsupported_resolution",
            oid=None,
            nspname=None,
            typname=None,
            detail="current_schema() is NULL; cannot resolve unqualified name",
        )

    rows = executor.fetch_all(
        "impact.resolve_type_candidates",
        (context.current_schemas_with_implicit, catalog_typname(name)),
    )
    candidates = _type_rows_to_candidates(rows)
    winner = rank_type_candidates(candidates, context.current_schemas_with_implicit)
    if winner is None:
        return TypeResolution(
            status="unsupported_resolution",
            oid=None,
            nspname=None,
            typname=None,
            detail="no candidate found under current_schemas(true)",
        )
    return TypeResolution(
        status="resolved",
        oid=winner.oid,
        nspname=winner.nspname,
        typname=winner.typname,
        detail=None,
    )


def resolve_function(
    *,
    schema: str | None,
    name: str,
    argtypes: tuple[int, ...],
    context: ResolutionContext,
    executor: QueryExecutor,
) -> FunctionResolution:
    """Resolve a (possibly schema-qualified) function name+argtypes to an oid.

    Ranking follows the same `current_schemas_with_implicit` first-match
    policy as relations/types (design section 2.4).
    """
    if _identifier_too_long(name, context):
        return FunctionResolution(
            status="unsupported_resolution",
            oid=None,
            nspname=None,
            proname=None,
            detail=f"identifier {name!r} exceeds max_identifier_length_bytes",
        )

    if schema is not None:
        rows = executor.fetch_all(
            "impact.resolve_function_candidates",
            ((schema,), name, argtypes, argtypes),
        )
        candidates = _function_rows_to_candidates(rows)
        if not candidates:
            return FunctionResolution(
                status="not_found", oid=None, nspname=None, proname=None, detail=None
            )
        chosen = candidates[0]
        return FunctionResolution(
            status="resolved",
            oid=chosen.oid,
            nspname=chosen.nspname,
            proname=chosen.proname,
            detail=None,
        )

    if context.current_schema is None:
        return FunctionResolution(
            status="unsupported_resolution",
            oid=None,
            nspname=None,
            proname=None,
            detail="current_schema() is NULL; cannot resolve unqualified name",
        )

    rows = executor.fetch_all(
        "impact.resolve_function_candidates",
        (context.current_schemas_with_implicit, name, argtypes, argtypes),
    )
    candidates = _function_rows_to_candidates(rows)
    winner = rank_function_candidates(candidates, context.current_schemas_with_implicit)
    if winner is None:
        return FunctionResolution(
            status="unsupported_resolution",
            oid=None,
            nspname=None,
            proname=None,
            detail="no candidate found under current_schemas(true)",
        )
    return FunctionResolution(
        status="resolved",
        oid=winner.oid,
        nspname=winner.nspname,
        proname=winner.proname,
        detail=None,
    )
