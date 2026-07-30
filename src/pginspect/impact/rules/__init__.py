"""`impact.rules` public surface.

Task 5 exports only `lookup_coercion` and `CoercionLookupResult`. Task 6
appends `RuleVerdict`, `apply_physical_invariants`, and
`aggregate_exit_code` from `severity.py` / `contracts.py`.
"""

from __future__ import annotations

from pginspect.impact.rules.coercion import CoercionLookupResult, lookup_coercion

__all__ = ["CoercionLookupResult", "lookup_coercion"]
