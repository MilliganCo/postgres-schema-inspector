"""`impact.rules` public surface.

Task 5 exports only `lookup_coercion` and `CoercionLookupResult`. Task 6
appends `RuleVerdict`, `apply_physical_invariants`, and
`aggregate_exit_code` from `severity.py` / `contracts.py`.
"""

from __future__ import annotations

from pginspect.impact.rules.coercion import CoercionLookupResult, lookup_coercion
from pginspect.impact.rules.contracts import RuleVerdict
from pginspect.impact.rules.severity import aggregate_exit_code, apply_physical_invariants

__all__ = [
    "CoercionLookupResult",
    "RuleVerdict",
    "aggregate_exit_code",
    "apply_physical_invariants",
    "lookup_coercion",
]
