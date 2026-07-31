"""QuerySpec lookup, the session execution seam, and the catalog executor.

This module does not import psycopg, does not hold a connection/cursor, and
does not expose a public `execute()` (design section 2.10). It provides:

- `get_spec`: a pure, immutable registry lookup. No caller can substitute
  different SQL text under an existing `query_id` — `get_spec` always
  returns the exact `QuerySpec` (and therefore the exact `LiteralString`
  SQL) stored in `IMPACT_QUERY_REGISTRY`.
- `execute_allowlisted`: the single execution seam. It takes a `query_id`
  (never SQL), rejects unknown ids and bad parameter arity/types *before*
  any database work, hands `spec.sql` to the session's private
  `_execute_allowlisted_query`, decodes the result through
  `spec.row_model`, and only then records what actually ran.
- `QueryExecutionEvent` / `QueryRecorder`: a uniform shape for recording one
  executed query (`query_id`, `sql_text`, `bound_parameters`,
  `command_kind`), emitted from the seam so the recorded timeline reflects
  real session invocations.
- `QueryExecutor` / `SessionQueryExecutor`: the abstract fetch surface that
  `resolve.py` and `catalog.py` depend on, plus the production adapter that
  implements it on top of a `DiagnosticSession`. Unit tests inject fakes
  implementing the protocol.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from pginspect.impact.queries import IMPACT_QUERY_REGISTRY, CommandKind, QuerySpec
from pginspect.impact.query_rows import decode_row, row_as_mapping

__all__ = [
    "UnknownQueryIdError",
    "ParameterValidationError",
    "get_spec",
    "QueryExecutionEvent",
    "QueryRecorder",
    "record_execution",
    "FetchMode",
    "AllowlistedQueryRunner",
    "validate_params",
    "execute_allowlisted",
    "QueryExecutor",
    "SessionQueryExecutor",
]

FetchMode = Literal["one", "all", "none"]

_FETCH_MODES: frozenset[str] = frozenset({"one", "all", "none"})


class UnknownQueryIdError(LookupError):
    """Raised when a `query_id` is not present in the immutable registry."""


class ParameterValidationError(ValueError):
    """Raised when bound parameters do not match `QuerySpec.param_types`."""


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


def validate_params(spec: QuerySpec, params: tuple[Any, ...]) -> None:
    """Reject parameter arity/type drift before any database work happens.

    `tuple` in `param_types` means "PostgreSQL array parameter". Callers may
    pass a Python `list` or `tuple` of elements; `normalize_array_params`
    converts tuples to lists before psycopg sees them, because a Python tuple
    is adapted as a composite/record rather than a text[].
    """
    if not isinstance(params, tuple):
        raise ParameterValidationError(
            f"{spec.query_id}: parameters must be a tuple, got {type(params).__name__}"
        )
    if len(params) != len(spec.param_types):
        raise ParameterValidationError(
            f"{spec.query_id}: expected {len(spec.param_types)} parameters, got {len(params)}"
        )
    for index, (value, expected) in enumerate(zip(params, spec.param_types, strict=True)):
        if expected is tuple:
            if not isinstance(value, (tuple, list)):
                raise ParameterValidationError(
                    f"{spec.query_id}: parameter {index} expected an array, "
                    f"got {type(value).__name__}"
                )
            continue
        if expected is int and isinstance(value, bool):
            raise ParameterValidationError(f"{spec.query_id}: parameter {index} expected int")
        if not isinstance(value, expected):
            raise ParameterValidationError(
                f"{spec.query_id}: parameter {index} expected {expected.__name__}, "
                f"got {type(value).__name__}"
            )


def normalize_array_params(spec: QuerySpec, params: tuple[Any, ...]) -> tuple[Any, ...]:
    """Ensure array-typed parameters are lists for psycopg array adaptation."""
    normalized: list[Any] = []
    for value, expected in zip(params, spec.param_types, strict=True):
        if expected is tuple and isinstance(value, tuple):
            normalized.append(list(value))
        else:
            normalized.append(value)
    return tuple(normalized)


@runtime_checkable
class AllowlistedQueryRunner(Protocol):
    """Narrow view of `DiagnosticSession` used by the execution seam.

    The only member is the private method that owns the cursor. Keeping the
    seam protocol-shaped means `query_exec` never imports `pginspect.session`
    (and therefore never reaches psycopg), while production code still runs
    every impact query through the real session.
    """

    def _execute_allowlisted_query(
        self,
        spec: QuerySpec,
        params: tuple[Any, ...],
        *,
        fetch: FetchMode,
    ) -> Any: ...


def execute_allowlisted(
    session: AllowlistedQueryRunner,
    query_id: str,
    params: tuple[Any, ...] = (),
    *,
    recorder: QueryRecorder | None = None,
    fetch: FetchMode = "one",
) -> Any:
    """Execute one allowlisted query against `session` and decode the result.

    There is deliberately no SQL parameter: the caller names a `query_id` and
    the seam supplies `spec.sql`. Unknown ids and parameter mismatches are
    rejected before the session is touched at all, and the recorder event is
    emitted only after the session actually ran the statement, so a recorded
    timeline is evidence of real execution rather than of intent.
    """
    spec = get_spec(query_id)
    if fetch not in _FETCH_MODES:
        raise ParameterValidationError(f"{spec.query_id}: unsupported fetch mode {fetch!r}")
    validate_params(spec, params)
    bound = normalize_array_params(spec, params)

    raw = session._execute_allowlisted_query(spec, bound, fetch=fetch)

    if recorder is not None:
        recorder(
            QueryExecutionEvent(
                query_id=spec.query_id,
                sql_text=spec.sql,
                bound_parameters=bound,
                command_kind=spec.command_kind,
            )
        )

    if fetch == "none":
        return None
    if spec.row_model is None:
        return raw
    if fetch == "all":
        return tuple(decode_row(spec.row_model, row) for row in raw or ())
    return None if raw is None else decode_row(spec.row_model, raw)


@runtime_checkable
class QueryExecutor(Protocol):
    """Abstract catalog/resolution executor injected into resolve/catalog.

    Implementations own the actual DB round trip; this package depends only
    on this protocol shape, so `resolve.py` / `catalog.py` never import
    psycopg or hold a connection. The production implementation is
    `SessionQueryExecutor`.
    """

    def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> Mapping[str, object] | None: ...

    def fetch_all(
        self, query_id: str, params: tuple[Any, ...]
    ) -> Sequence[Mapping[str, object]]: ...


@dataclass(frozen=True)
class SessionQueryExecutor:
    """Production `QueryExecutor` backed by a `DiagnosticSession`.

    Rows are decoded through `QuerySpec.row_model` first, so every column
    reaching `catalog.py` / `resolve.py` has already been validated against
    the model that matches the registry SQL aliases.
    """

    session: AllowlistedQueryRunner
    recorder: QueryRecorder | None = None

    def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> Mapping[str, object] | None:
        row = execute_allowlisted(
            self.session, query_id, params, recorder=self.recorder, fetch="one"
        )
        return None if row is None else row_as_mapping(row)

    def fetch_all(self, query_id: str, params: tuple[Any, ...]) -> Sequence[Mapping[str, object]]:
        rows = execute_allowlisted(
            self.session, query_id, params, recorder=self.recorder, fetch="all"
        )
        return tuple(row_as_mapping(row) for row in rows)
