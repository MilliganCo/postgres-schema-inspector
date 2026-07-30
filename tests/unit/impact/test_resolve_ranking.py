"""Unit tests for `impact.resolve`: current_schemas(true) ranking only.

No live PostgreSQL connection: `QueryExecutor` is a fake that returns
pre-canned rows per `query_id`, so these tests exercise the pure ranking
and resolution-outcome logic (design section 2.4).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from pginspect.impact.preflight import ResolutionContext
from pginspect.impact.resolve import (
    FunctionCandidate,
    RelationCandidate,
    TypeCandidate,
    rank_function_candidates,
    rank_relation_candidates,
    rank_type_candidates,
    resolve_function,
    resolve_relation,
    resolve_type,
)


class _FakeExecutor:
    def __init__(self, responses: Mapping[str, Sequence[Mapping[str, object]]]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> Mapping[str, object] | None:
        self.calls.append((query_id, params))
        rows = self._responses.get(query_id, ())
        return rows[0] if rows else None

    def fetch_all(self, query_id: str, params: tuple[Any, ...]) -> Sequence[Mapping[str, object]]:
        self.calls.append((query_id, params))
        return self._responses.get(query_id, ())


def _context(
    *,
    current_schema: str | None = "app",
    current_schemas_with_implicit: tuple[str, ...] = ("app", "pg_catalog"),
    max_identifier_length_bytes: int = 63,
) -> ResolutionContext:
    return ResolutionContext(
        database="db",
        role="role",
        session_user="role",
        current_schema=current_schema,
        current_schemas_user=(current_schema,) if current_schema else (),
        current_schemas_with_implicit=current_schemas_with_implicit,
        search_path_raw="app",
        max_identifier_length_bytes=max_identifier_length_bytes,
        server_major=16,
        server_version_num=160004,
        keyword_categories={},
    )


# --- Pure ranking helpers -------------------------------------------------


def test_rank_relation_candidates_first_match_wins() -> None:
    ordering = ("app_a", "app_b", "pg_catalog")
    candidates = [
        RelationCandidate(oid=2, nspname="app_b", relname="t"),
        RelationCandidate(oid=1, nspname="app_a", relname="t"),
    ]
    winner = rank_relation_candidates(candidates, ordering)
    assert winner is not None
    assert winner.oid == 1
    assert winner.nspname == "app_a"


def test_rank_relation_candidates_ignores_schemas_outside_ordering() -> None:
    ordering = ("app_a",)
    candidates = [RelationCandidate(oid=9, nspname="unrelated", relname="t")]
    assert rank_relation_candidates(candidates, ordering) is None


def test_rank_type_and_function_candidates_use_same_ranking() -> None:
    ordering = ("a", "b")
    type_candidates = [
        TypeCandidate(oid=2, nspname="b", typname="mytype"),
        TypeCandidate(oid=1, nspname="a", typname="mytype"),
    ]
    assert rank_type_candidates(type_candidates, ordering).oid == 1  # type: ignore[union-attr]

    func_candidates = [
        FunctionCandidate(oid=2, nspname="b", proname="f"),
        FunctionCandidate(oid=1, nspname="a", proname="f"),
    ]
    assert rank_function_candidates(func_candidates, ordering).oid == 1  # type: ignore[union-attr]


# --- resolve_relation ------------------------------------------------------


def test_resolve_relation_qualified_found() -> None:
    executor = _FakeExecutor(
        {"impact.resolve_relation_candidates": [{"oid": 42, "nspname": "app", "relname": "t"}]}
    )
    result = resolve_relation(schema="app", name="t", context=_context(), executor=executor)
    assert result.status == "resolved"
    assert result.oid == 42
    assert executor.calls == [("impact.resolve_relation_candidates", (("app",), "t"))]


def test_resolve_relation_qualified_missing_is_deterministic_not_found() -> None:
    executor = _FakeExecutor({"impact.resolve_relation_candidates": []})
    result = resolve_relation(schema="app", name="missing", context=_context(), executor=executor)
    assert result.status == "not_found"
    assert result.oid is None


def test_resolve_relation_unqualified_first_match_in_current_schema_resolves() -> None:
    executor = _FakeExecutor(
        {
            "impact.resolve_relation_candidates": [
                {"oid": 1, "nspname": "app", "relname": "t"},
            ]
        }
    )
    context = _context(current_schema="app", current_schemas_with_implicit=("app", "pg_catalog"))
    result = resolve_relation(schema=None, name="t", context=context, executor=executor)
    assert result.status == "resolved"
    assert result.oid == 1
    assert result.nspname == "app"


def test_resolve_relation_unqualified_shadowed_by_earlier_schema_is_unsupported() -> None:
    """`impact_s2_b.t` must not win when `impact_s2_a` ranks first (S2_shadow)."""
    executor = _FakeExecutor(
        {
            "impact.resolve_relation_candidates": [
                {"oid": 1, "nspname": "impact_s2_a", "relname": "t"},
                {"oid": 2, "nspname": "impact_s2_b", "relname": "t"},
            ]
        }
    )
    context = _context(
        current_schema="impact_s2_b",
        current_schemas_with_implicit=("impact_s2_a", "impact_s2_b", "pg_catalog"),
    )
    result = resolve_relation(schema=None, name="t", context=context, executor=executor)
    assert result.status == "unsupported_resolution"
    assert result.oid is None


def test_resolve_relation_unqualified_first_match_is_target_schema_not_shadowed() -> None:
    executor = _FakeExecutor(
        {
            "impact.resolve_relation_candidates": [
                {"oid": 1, "nspname": "impact_s2_a", "relname": "t"},
                {"oid": 2, "nspname": "impact_s2_b", "relname": "t"},
            ]
        }
    )
    context = _context(
        current_schema="impact_s2_a",
        current_schemas_with_implicit=("impact_s2_a", "impact_s2_b", "pg_catalog"),
    )
    result = resolve_relation(schema=None, name="t", context=context, executor=executor)
    assert result.status == "resolved"
    assert result.oid == 1
    assert result.nspname == "impact_s2_a"


def test_resolve_relation_unqualified_no_candidates_is_unsupported_not_deterministic() -> None:
    executor = _FakeExecutor({"impact.resolve_relation_candidates": []})
    result = resolve_relation(schema=None, name="ghost", context=_context(), executor=executor)
    assert result.status == "unsupported_resolution"


def test_resolve_relation_unqualified_with_null_current_schema_is_unsupported() -> None:
    executor = _FakeExecutor({"impact.resolve_relation_candidates": []})
    context = _context(current_schema=None, current_schemas_with_implicit=("pg_catalog",))
    result = resolve_relation(schema=None, name="t", context=context, executor=executor)
    assert result.status == "unsupported_resolution"
    # current_schema is NULL: resolver must reject before even issuing a query.
    assert executor.calls == []


def test_resolve_relation_over_long_identifier_is_unsupported_resolution() -> None:
    executor = _FakeExecutor({})
    context = _context(max_identifier_length_bytes=8)
    result = resolve_relation(
        schema="app", name="way_too_long_name", context=context, executor=executor
    )
    assert result.status == "unsupported_resolution"
    assert executor.calls == []


# --- resolve_type / resolve_function ---------------------------------------


def test_resolve_type_unqualified_ranks_without_current_schema_requirement() -> None:
    executor = _FakeExecutor(
        {
            "impact.resolve_type_candidates": [
                {"oid": 5, "nspname": "pg_catalog", "typname": "mytype"},
            ]
        }
    )
    context = _context(current_schema="app", current_schemas_with_implicit=("app", "pg_catalog"))
    result = resolve_type(schema=None, name="mytype", context=context, executor=executor)
    assert result.status == "resolved"
    assert result.oid == 5
    assert result.nspname == "pg_catalog"


def test_resolve_type_unqualified_not_found_is_unsupported_resolution() -> None:
    executor = _FakeExecutor({"impact.resolve_type_candidates": []})
    result = resolve_type(schema=None, name="ghost", context=_context(), executor=executor)
    assert result.status == "unsupported_resolution"


def test_resolve_function_qualified_found_passes_argtypes_param() -> None:
    executor = _FakeExecutor(
        {
            "impact.resolve_function_candidates": [
                {"oid": 99, "nspname": "pg_catalog", "proname": "clock_timestamp"},
            ]
        }
    )
    result = resolve_function(
        schema="pg_catalog",
        name="clock_timestamp",
        argtypes=(),
        context=_context(),
        executor=executor,
    )
    assert result.status == "resolved"
    assert result.oid == 99
    assert executor.calls == [
        ("impact.resolve_function_candidates", (("pg_catalog",), "clock_timestamp", ()))
    ]


@pytest.mark.parametrize("schema", [None, "app"])
def test_resolve_function_missing_never_invents_an_oid(schema: str | None) -> None:
    executor = _FakeExecutor({"impact.resolve_function_candidates": []})
    result = resolve_function(
        schema=schema, name="ghost", argtypes=(), context=_context(), executor=executor
    )
    assert result.oid is None
    assert result.status in ("not_found", "unsupported_resolution")
