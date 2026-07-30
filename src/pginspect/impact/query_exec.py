"""QuerySpec lookup, execution recorder, and abstract catalog executor.

This module does not import psycopg, does not hold a connection/cursor, and
does not expose a public `execute()` (design section 2.10). It provides:

- `get_spec`: a pure, immutable registry lookup. No caller can substitute
  different SQL text under an existing `query_id` — `get_spec` always
  returns the exact `QuerySpec` (and therefore the exact `LiteralString`
  SQL) stored in `IMPACT_QUERY_REGISTRY`.
- `QueryExecutionEvent` / `QueryRecorder` / `record_execution`: a uniform
  shape for recording one executed query (`query_id`, `sql_text`,
  `bound_parameters`, `command_kind`), independent of who performs the
  actual DB round trip.
- `QueryExecutor`: the abstract fetch surface that `resolve.py` and
  `catalog.py` depend on. Production wiring (backed by `DiagnosticSession`)
  is supplied by the orchestration layer outside `impact/*`; unit tests
  inject fakes implementing this protocol.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pginspect.impact.queries import IMPACT_QUERY_REGISTRY, CommandKind, QuerySpec

__all__ = [
    "UnknownQueryIdError",
    "get_spec",
    "QueryExecutionEvent",
    "QueryRecorder",
    "record_execution",
    "QueryExecutor",
]


class UnknownQueryIdError(LookupError):
    """Raised when a `query_id` is not present in the immutable registry."""


def get_spec(query_id: str) -> QuerySpec:
    """Look up an allowlisted `QuerySpec` by id.

    This is the only sanctioned way to obtain SQL text for execution:
    callers pass `query_id` around, never raw SQL, so the executed text is
    always exactly the registry's `LiteralString`.
    """
    try:
        return IMPACT_QUERY_REGISTRY[query_id]
    except KeyError:
        raise UnknownQueryIdError(query_id) from None


@dataclass(frozen=True)
class QueryExecutionEvent:
    query_id: str
    sql_text: str
    bound_parameters: tuple[Any, ...]
    command_kind: CommandKind


QueryRecorder = Callable[[QueryExecutionEvent], None]


def record_execution(
    recorder: QueryRecorder | None,
    query_id: str,
    bound_parameters: tuple[Any, ...],
) -> QuerySpec:
    """Resolve `query_id` to its allowlisted spec and emit a recorder event.

    Returns the `QuerySpec` so the caller executes `spec.sql` verbatim.
    Bound parameters may carry object names taken from the migration text,
    but the SQL text itself is always the fixed, package-owned constant.
    """
    spec = get_spec(query_id)
    if recorder is not None:
        recorder(
            QueryExecutionEvent(
                query_id=spec.query_id,
                sql_text=spec.sql,
                bound_parameters=bound_parameters,
                command_kind=spec.command_kind,
            )
        )
    return spec


@runtime_checkable
class QueryExecutor(Protocol):
    """Abstract catalog/resolution executor injected into resolve/catalog.

    Implementations own the actual DB round trip (and typically call
    `record_execution` internally); this package depends only on this
    protocol shape, so `resolve.py` / `catalog.py` never import psycopg or
    hold a connection.
    """

    def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> Mapping[str, object] | None: ...

    def fetch_all(
        self, query_id: str, params: tuple[Any, ...]
    ) -> Sequence[Mapping[str, object]]: ...
