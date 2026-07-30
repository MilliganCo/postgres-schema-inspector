"""Full QuerySpec inventory presence + immutability (plan Task 5)."""

from __future__ import annotations

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


def test_command_kinds_are_valid_and_row_model_none_for_all_current_specs() -> None:
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

    for spec in IMPACT_QUERY_REGISTRY.values():
        assert spec.command_kind in ("SELECT", "SET", "BEGIN")
        assert spec.row_model is None


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
        "impact.fetch_relation_metrics",
        "impact.fetch_pg_cast",
    }
    for query_id in catalog_ids:
        sql = IMPACT_QUERY_REGISTRY[query_id].sql
        assert "FROM pg_catalog." in sql or "FROM target" in sql
