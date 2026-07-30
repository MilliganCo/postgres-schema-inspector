"""T1-T3 fixed-origin coercion evidence (plan Task 5).

No live PostgreSQL: `lookup_coercion` is a pure function over type-name
pairs plus caller-supplied `PgCastRow` facts standing in for a live
`impact.fetch_pg_cast` result.
"""

from __future__ import annotations

from pginspect.impact.models.catalog_types import PgCastRow
from pginspect.impact.rules import CoercionLookupResult, lookup_coercion
from pginspect.impact.rules.coercion import lookup_coercion as lookup_coercion_direct


def test_public_rules_surface_exports_coercion_symbols() -> None:
    import pginspect.impact.rules as rules_pkg

    assert {"CoercionLookupResult", "lookup_coercion"} <= set(rules_pkg.__all__)
    assert lookup_coercion is lookup_coercion_direct


# --- T1: integer -> text (server_generic_rule, automatic_io) --------------


def test_t1_integer_to_text_is_always_found_without_pg_cast() -> None:
    result = lookup_coercion("integer", "text", context="assignment")
    assert result.status == "found"
    assert result.method == "automatic_io"
    assert result.origin == "server_generic_rule"
    assert result.evidence_id == "coercion:integer_to_text_assignment"


def test_t1_integer_to_text_never_consults_or_requires_pg_cast_rows() -> None:
    """Never invents a pg_cast row: presence/absence of pg_cast_rows must not matter."""
    without_rows = lookup_coercion("integer", "text", context="assignment", pg_cast_rows=())
    with_unrelated_rows = lookup_coercion(
        "integer",
        "text",
        context="assignment",
        pg_cast_rows=(
            PgCastRow(castsource=1, casttarget=2, castfunc=0, castcontext="e", castmethod="f"),
        ),
    )
    assert without_rows == with_unrelated_rows
    assert without_rows.origin == "server_generic_rule"


def test_t1_case_and_whitespace_insensitive_type_names() -> None:
    result = lookup_coercion("  INTEGER ", " Text", context="assignment")
    assert result.status == "found"


# --- T2: text -> varchar (pg_cast, binary) ---------------------------------


def test_t2_text_to_varchar_found_when_live_binary_cast_row_present() -> None:
    binary_row = PgCastRow(
        castsource=25, casttarget=1043, castfunc=0, castcontext="i", castmethod="b"
    )
    result = lookup_coercion("text", "varchar", context="assignment", pg_cast_rows=(binary_row,))
    assert result.status == "found"
    assert result.method == "binary"
    assert result.origin == "pg_cast"
    assert result.evidence_id == "coercion:text_to_varchar_binary"


def test_t2_text_to_varchar_unsupported_evidence_when_pg_cast_row_missing() -> None:
    result = lookup_coercion("text", "varchar", context="assignment", pg_cast_rows=())
    assert result.status == "unsupported_evidence"
    assert result.evidence_id is None


def test_t2_text_to_varchar_unsupported_evidence_when_cast_is_not_binary() -> None:
    function_row = PgCastRow(
        castsource=25, casttarget=1043, castfunc=123, castcontext="a", castmethod="f"
    )
    result = lookup_coercion("text", "varchar", context="assignment", pg_cast_rows=(function_row,))
    assert result.status == "unsupported_evidence"


# --- T3: text -> integer, no USING (checked_in_rule absence) --------------


def test_t3_text_to_integer_absence_is_checked_in_rule_when_no_cast_exists() -> None:
    result = lookup_coercion("text", "integer", context="assignment", pg_cast_rows=())
    assert result.status == "checked_in_absence"
    assert result.origin == "checked_in_rule"
    assert result.rule_key == "type.no_assignment_cast.no_using"
    assert result.evidence_id is None


def test_t3_text_to_integer_unsupported_evidence_if_unexpected_cast_appears() -> None:
    unexpected_row = PgCastRow(
        castsource=25, casttarget=23, castfunc=999, castcontext="a", castmethod="f"
    )
    result = lookup_coercion(
        "text", "integer", context="assignment", pg_cast_rows=(unexpected_row,)
    )
    assert result.status == "unsupported_evidence"


def test_t3_explicit_only_cast_does_not_trigger_unsupported_evidence() -> None:
    """An explicit-only cast (e.g. `::integer`) does not contradict the no-assignment-cast rule."""
    explicit_row = PgCastRow(
        castsource=25, casttarget=23, castfunc=999, castcontext="e", castmethod="f"
    )
    result = lookup_coercion("text", "integer", context="assignment", pg_cast_rows=(explicit_row,))
    assert result.status == "checked_in_absence"


# --- Unknown pairs ----------------------------------------------------------


def test_unknown_pair_is_reported_as_unknown_not_invented() -> None:
    result = lookup_coercion("boolean", "text", context="assignment")
    assert result.status == "unknown_pair"
    assert result.evidence_id is None
    assert result.rule_key is None


def test_lookup_coercion_result_is_frozen_dataclass() -> None:
    result = lookup_coercion("integer", "text", context="assignment")
    assert isinstance(result, CoercionLookupResult)
    try:
        result.status = "unknown_pair"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("CoercionLookupResult must be frozen")
