"""Sequence constraints over resolved `AnalysisUnit`s (design section 1.6).

The parser keeps no virtual schema state, so a statement whose resolution
would depend on the effect of an earlier statement in the same input cannot
be resolved against the live catalog. `apply_sequence_constraints` runs
after resolution and before risk scoring / `ImpactStatementCard` assembly:
it marks such dependents `unsupported_sequence` and keeps the earlier,
independently analyzable units untouched.

Normative matrix (design section 1.6):

| Prior statement          | Later statement                                 |
|--------------------------|-------------------------------------------------|
| `ADD COLUMN x`           | later `ALTER TYPE` / `DROP` of `x` on the table  |
| `DROP COLUMN x`          | later reference to `x` on the same table         |
| `ALTER COLUMN x TYPE`    | later op resolving against the new type of `x`   |
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from pginspect.impact.analysis_unit import AnalysisUnit
from pginspect.impact.models.enums import AnalysisStatus

SEQUENCE_DEPENDENCY_LIMITATION = (
    "Resolution depends on schema state produced by an earlier statement in the same input; "
    "virtual schema state is not modeled."
)

__all__ = ["SEQUENCE_DEPENDENCY_LIMITATION", "apply_sequence_constraints"]

_MUTATING_FAMILIES = frozenset({"add", "drop", "type"})


def apply_sequence_constraints(units: Sequence[AnalysisUnit]) -> tuple[AnalysisUnit, ...]:
    """Mark dependents `unsupported_sequence` per design section 1.6.

    Units are visited in statement order (`statement_index` ascending) but
    returned in the order they were given. Only a unit that is still
    `analyzed` is marked: an already-unsupported unit keeps the status that
    explains why it was dropped first.
    """
    marked = list(units)
    mutated_keys: set[str] = set()
    for position in sorted(range(len(units)), key=lambda i: (units[i].statement_index, i)):
        unit = units[position]
        keys = _identity_keys(unit)
        if keys & mutated_keys and unit.analysis_status is AnalysisStatus.ANALYZED:
            marked[position] = _mark_unsupported_sequence(unit)
        if unit.family in _MUTATING_FAMILIES:
            mutated_keys |= keys
    return tuple(marked)


def _identity_keys(unit: AnalysisUnit) -> frozenset[str]:
    """Column identities this unit is about, as comparable keys.

    OID identity wins when the table was resolved; a unit may carry both a
    name key and an attnum key, and matching either one is a match. Units
    resolved by name only (no `table_oid`) fall back to the qualified table
    name so pre-resolution sequencing still works.
    """
    column = unit.column_normalized_name
    if unit.table_oid is not None:
        keys: set[str] = set()
        if column is not None:
            keys.add(f"oid:{unit.table_oid}|col:{column}")
        if unit.column_attnum is not None:
            keys.add(f"oid:{unit.table_oid}|attnum:{unit.column_attnum}")
        return frozenset(keys)
    if unit.table_schema is not None and unit.table_name is not None and column is not None:
        return frozenset({f"name:{unit.table_schema}.{unit.table_name}|col:{column}"})
    return frozenset()


def _mark_unsupported_sequence(unit: AnalysisUnit) -> AnalysisUnit:
    limitations = unit.limitations
    if SEQUENCE_DEPENDENCY_LIMITATION not in limitations:
        limitations = (*limitations, SEQUENCE_DEPENDENCY_LIMITATION)
    return replace(
        unit,
        analysis_status=AnalysisStatus.UNSUPPORTED_SEQUENCE,
        limitations=limitations,
    )
