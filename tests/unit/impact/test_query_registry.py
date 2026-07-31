"""Full QuerySpec inventory presence, immutability, and row-model decoding."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from types import UnionType
from typing import Literal, Union, get_args, get_origin, get_type_hints

import pytest


def test_registry_contains_required_query_ids() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    required = {
        "impact.begin_read_only_rr",
        "impact.set_timeouts",
        "impact.capture_resolution_context",
        "impact.harden_search_path",
        "impact.verify_safety",
        "impact.preflight_reads",
        "impact.resolve_relation_candidates",
        "impact.resolve_type_candidates",
        "impact.resolve_function_candidates",
        "impact.fetch_relation",
        "impact.fetch_columns",
        "impact.fetch_type",
        "impact.fetch_domain_constraints",
        "impact.fetch_indexes",
        "impact.fetch_constraints",
        "impact.fetch_function",
        "impact.fetch_dependency_edges",
        "impact.fetch_pg_class_classoid",
        "impact.fetch_rewrite_ev_class",
        "impact.fetch_relation_metrics",
        "impact.fetch_pg_cast",
    }
    assert required <= set(IMPACT_QUERY_REGISTRY)


def test_registry_is_immutable_mapping_proxy() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    with pytest.raises(TypeError):
        IMPACT_QUERY_REGISTRY["impact.begin_read_only_rr"] = None  # type: ignore[index]


def test_query_spec_dataclass_is_frozen() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    spec = IMPACT_QUERY_REGISTRY["impact.fetch_relation"]
    with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises FrozenInstanceError
        spec.sql = "SELECT 1"  # type: ignore[misc]


def test_every_query_id_maps_to_matching_spec_query_id() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    for query_id, spec in IMPACT_QUERY_REGISTRY.items():
        assert spec.query_id == query_id


def test_command_kinds_are_valid() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    for spec in IMPACT_QUERY_REGISTRY.values():
        assert spec.command_kind in ("SELECT", "SET", "BEGIN")


def test_only_discarded_specs_may_omit_a_row_model() -> None:
    """`row_model=None` is allowed only where the result is intentionally dropped."""
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    without_model = {
        query_id for query_id, spec in IMPACT_QUERY_REGISTRY.items() if spec.row_model is None
    }
    assert without_model == {
        "impact.begin_read_only_rr",
        "impact.set_timeouts",
        "impact.harden_search_path",
    }


def test_every_select_except_set_timeouts_has_a_concrete_row_model() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    for query_id, spec in IMPACT_QUERY_REGISTRY.items():
        if spec.command_kind != "SELECT" or query_id == "impact.set_timeouts":
            continue
        assert isinstance(spec.row_model, type), query_id
        assert dataclasses.is_dataclass(spec.row_model), query_id


def test_expected_row_models_are_wired_to_their_query_ids() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    expected = {
        "impact.capture_resolution_context": "ResolutionCaptureRow",
        "impact.verify_safety": "SafetyVerifyRow",
        "impact.preflight_reads": "PreflightRow",
        "impact.resolve_relation_candidates": "RelationCandidateRow",
        "impact.resolve_type_candidates": "TypeCandidateRow",
        "impact.resolve_function_candidates": "FunctionCandidateRow",
        "impact.fetch_relation": "RelationRow",
        "impact.fetch_columns": "ColumnRow",
        "impact.fetch_type": "TypeRow",
        "impact.fetch_domain_constraints": "DomainConstraintRow",
        "impact.fetch_indexes": "IndexRow",
        "impact.fetch_constraints": "ConstraintRow",
        "impact.fetch_function": "FunctionRow",
        "impact.fetch_dependency_edges": "DependencyEdgeRow",
        "impact.fetch_pg_class_classoid": "CatalogClassOidRow",
        "impact.fetch_rewrite_ev_class": "RewriteEvClassRow",
        "impact.fetch_relation_metrics": "RelationMetricsRow",
        "impact.fetch_pg_cast": "PgCastRow",
    }
    for query_id, model_name in expected.items():
        row_model = IMPACT_QUERY_REGISTRY[query_id].row_model
        assert row_model is not None
        assert row_model.__name__ == model_name


def test_every_row_model_is_frozen() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    for spec in IMPACT_QUERY_REGISTRY.values():
        if spec.row_model is None:
            continue
        assert spec.row_model.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
        instance = _sample_instance(spec.row_model)
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, dataclasses.fields(spec.row_model)[0].name, None)


def test_row_model_field_names_match_sql_aliases() -> None:
    """Every model field must appear as an `AS <name>` alias in its SQL."""
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    for query_id, spec in IMPACT_QUERY_REGISTRY.items():
        if spec.row_model is None:
            continue
        # Drop CTE bodies: only the outer SELECT list defines the row contract.
        outer_sql = re.sub(r"WITH\s+\w+\s+AS\s*\([^()]*\)", " ", spec.sql, flags=re.IGNORECASE)
        aliases = set(re.findall(r"\bAS\s+(\w+)", outer_sql))
        field_names = {field.name for field in dataclasses.fields(spec.row_model)}
        assert field_names == aliases, query_id


def _sample_value(annotation: object) -> object:
    origin = get_origin(annotation)
    if origin is Literal:
        return get_args(annotation)[0]
    if origin is Union or origin is UnionType:
        return _sample_value(next(arg for arg in get_args(annotation) if arg is not type(None)))
    if origin is tuple:
        return (_sample_value(get_args(annotation)[0]),)
    if isinstance(origin, type) and issubclass(origin, Mapping):
        return {"word": "R"}
    if annotation is bool:
        return True
    if annotation is int:
        return 1
    return "x"


def _sample_row(model: type) -> dict[str, object]:
    hints = get_type_hints(model)
    return {field.name: _sample_value(hints[field.name]) for field in dataclasses.fields(model)}


def _sample_instance(model: type) -> object:
    from pginspect.impact.query_rows import decode_row

    return decode_row(model, _sample_row(model))


def test_every_row_model_decodes_a_well_formed_row() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY
    from pginspect.impact.query_rows import decode_row

    for spec in IMPACT_QUERY_REGISTRY.values():
        if spec.row_model is None:
            continue
        row = _sample_row(spec.row_model)
        assert isinstance(decode_row(spec.row_model, row), spec.row_model)


def test_decode_rejects_missing_extra_and_invalid_fields() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY
    from pginspect.impact.query_rows import RowDecodeError, decode_row

    for spec in IMPACT_QUERY_REGISTRY.values():
        if spec.row_model is None:
            continue
        base = _sample_row(spec.row_model)
        first = dataclasses.fields(spec.row_model)[0].name

        missing = {k: v for k, v in base.items() if k != first}
        with pytest.raises(RowDecodeError):
            decode_row(spec.row_model, missing)

        extra = dict(base, unexpected_column=1)
        with pytest.raises(RowDecodeError):
            decode_row(spec.row_model, extra)

        invalid = dict(base, **{first: object()})
        with pytest.raises(RowDecodeError):
            decode_row(spec.row_model, invalid)


def test_decode_rejects_null_in_non_optional_field() -> None:
    from pginspect.impact.query_rows import RelationCandidateRow, RowDecodeError, decode_row

    with pytest.raises(RowDecodeError):
        decode_row(RelationCandidateRow, {"oid": None, "nspname": "public", "relname": "t"})


def test_decode_rejects_bool_for_int_field() -> None:
    from pginspect.impact.query_rows import RelationCandidateRow, RowDecodeError, decode_row

    with pytest.raises(RowDecodeError):
        decode_row(RelationCandidateRow, {"oid": True, "nspname": "public", "relname": "t"})


def test_decode_normalizes_postgres_arrays_to_tuples() -> None:
    from pginspect.impact.query_rows import RelationRow, decode_row

    row = decode_row(
        RelationRow,
        {
            "oid": 1,
            "nspname": "public",
            "relname": "t",
            "relkind": "r",
            "relpersistence": "p",
            "relispartition": False,
            "inherits_parents": [2, 3],
            "inherits_children": [],
        },
    )
    assert row.inherits_parents == (2, 3)
    assert row.inherits_children == ()


def test_row_as_mapping_is_immutable_and_complete() -> None:
    from pginspect.impact.query_rows import RelationCandidateRow, decode_row, row_as_mapping

    row = decode_row(RelationCandidateRow, {"oid": 1, "nspname": "public", "relname": "t"})
    mapping = row_as_mapping(row)
    assert dict(mapping) == {"oid": 1, "nspname": "public", "relname": "t"}
    with pytest.raises(TypeError):
        mapping["oid"] = 2  # type: ignore[index]


def test_catalog_query_sql_is_schema_qualified_pg_catalog() -> None:
    """Every catalog-object read table reference is `pg_catalog.<table>`."""
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    catalog_ids = {
        "impact.resolve_relation_candidates",
        "impact.resolve_type_candidates",
        "impact.resolve_function_candidates",
        "impact.fetch_relation",
        "impact.fetch_columns",
        "impact.fetch_type",
        "impact.fetch_domain_constraints",
        "impact.fetch_indexes",
        "impact.fetch_constraints",
        "impact.fetch_function",
        "impact.fetch_dependency_edges",
        "impact.fetch_pg_class_classoid",
        "impact.fetch_relation_metrics",
        "impact.fetch_pg_cast",
    }
    for query_id in catalog_ids:
        sql = IMPACT_QUERY_REGISTRY[query_id].sql
        assert "FROM pg_catalog." in sql or "FROM target" in sql
