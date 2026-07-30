"""Fixed-origin T1-T3 coercion evidence lookup (plan Task 5, design section 2.8).

Only the three pairs below have a normative, checked-in origin at this
stage. Every other source/target pair is out of scope for `lookup_coercion`
and must be resolved by the general TYPE rule engine (Task 7) against live
catalog evidence. `pg_cast` is necessary but not sufficient: a coercion
path may also come from a server generic rule (e.g. automatic I/O to text)
or a checked-in absence rule. Inventing a `pg_cast` row that the live
catalog does not contain is forbidden — the `text -> varchar` case only
reports `found` when a caller-supplied live row actually proves it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pginspect.impact.models.catalog_types import CoercionMethod, CoercionOrigin, PgCastRow

CoercionLookupStatus = Literal[
    "found",
    "checked_in_absence",
    "unsupported_evidence",
    "unknown_pair",
]

__all__ = ["CoercionLookupResult", "lookup_coercion"]

_INTEGER_TO_TEXT_EVIDENCE_ID = "coercion:integer_to_text_assignment"
_TEXT_TO_VARCHAR_EVIDENCE_ID = "coercion:text_to_varchar_binary"
_TEXT_TO_INTEGER_NO_USING_RULE_KEY = "type.no_assignment_cast.no_using"

_BINARY_CAST_METHOD = "b"


@dataclass(frozen=True)
class CoercionLookupResult:
    status: CoercionLookupStatus
    method: CoercionMethod | None
    origin: CoercionOrigin | None
    evidence_id: str | None
    rule_key: str | None
    detail: str | None


def _found(
    *, method: CoercionMethod, origin: CoercionOrigin, evidence_id: str
) -> CoercionLookupResult:
    return CoercionLookupResult(
        status="found",
        method=method,
        origin=origin,
        evidence_id=evidence_id,
        rule_key=None,
        detail=None,
    )


def _unsupported_evidence(detail: str) -> CoercionLookupResult:
    return CoercionLookupResult(
        status="unsupported_evidence",
        method=None,
        origin=None,
        evidence_id=None,
        rule_key=None,
        detail=detail,
    )


def lookup_coercion(
    source_type_name: str,
    target_type_name: str,
    *,
    context: Literal["implicit", "assignment", "explicit"],
    pg_cast_rows: Sequence[PgCastRow] = (),
) -> CoercionLookupResult:
    """Resolve the fixed-origin T1-T3 coercion fact for one type-name pair.

    - `integer -> text`: always `found` (`automatic_io` /
      `server_generic_rule`); `pg_cast_rows` is not consulted — this path
      never depends on (and never invents) a `pg_cast` row.
    - `text -> varchar`: `found` (`binary` / `pg_cast`) only when
      `pg_cast_rows` contains a live binary-coercible row; otherwise
      `unsupported_evidence`.
    - `text -> integer`: `checked_in_absence` (no assignment cast exists)
      when `pg_cast_rows` shows no unexpected assignment/implicit cast;
      `unsupported_evidence` if the live catalog unexpectedly proves one.
    - Any other pair: `unknown_pair` (handled by the general TYPE rule
      engine, out of scope here).
    """
    source = source_type_name.strip().lower()
    target = target_type_name.strip().lower()

    if source == "integer" and target == "text":
        return _found(
            method="automatic_io",
            origin="server_generic_rule",
            evidence_id=_INTEGER_TO_TEXT_EVIDENCE_ID,
        )

    if source == "text" and target == "varchar":
        binary_row = next(
            (row for row in pg_cast_rows if row.castmethod == _BINARY_CAST_METHOD),
            None,
        )
        if binary_row is None:
            return _unsupported_evidence(
                "live pg_cast row for text->varchar missing or not binary-coercible"
            )
        return _found(
            method="binary",
            origin="pg_cast",
            evidence_id=_TEXT_TO_VARCHAR_EVIDENCE_ID,
        )

    if source == "text" and target == "integer":
        unexpected = [row for row in pg_cast_rows if row.castcontext in ("a", "i")]
        if unexpected:
            return _unsupported_evidence(
                "unexpected assignment/implicit pg_cast found for text->integer"
            )
        return CoercionLookupResult(
            status="checked_in_absence",
            method=None,
            origin="checked_in_rule",
            evidence_id=None,
            rule_key=_TEXT_TO_INTEGER_NO_USING_RULE_KEY,
            detail=None,
        )

    return CoercionLookupResult(
        status="unknown_pair",
        method=None,
        origin=None,
        evidence_id=None,
        rule_key=None,
        detail=f"no fixed T1-T3 coercion origin for {source}->{target}",
    )
