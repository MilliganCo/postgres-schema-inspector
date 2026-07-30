"""The `query_exec` seam is the only route from impact code to a cursor.

These tests pin the guarantees the seam exists to provide: an unknown
`query_id` or a bad parameter list must be rejected *before* the database is
touched, the caller has no way to substitute SQL text, the executed SQL is
byte-identical to the registry `QuerySpec`, and a recorded event is evidence
of a real session invocation rather than of intent.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pginspect.config import SessionSafetyConfig
from pginspect.impact.queries import IMPACT_QUERY_REGISTRY, QuerySpec
from pginspect.impact.query_exec import (
    ParameterValidationError,
    QueryExecutionEvent,
    QueryExecutor,
    SessionQueryExecutor,
    UnknownQueryIdError,
    execute_allowlisted,
)
from pginspect.impact.query_rows import RelationCandidateRow, RelationRow
from pginspect.session import DiagnosticSession, SessionState

SRC_IMPACT = Path(__file__).resolve().parents[3] / "src" / "pginspect" / "impact"


class _SpyRunner:
    """Minimal `AllowlistedQueryRunner` recording what the seam handed it."""

    def __init__(self, result: Any = None) -> None:
        self.result = result
        self.calls: list[tuple[QuerySpec, tuple[Any, ...], str]] = []

    def _execute_allowlisted_query(
        self,
        spec: QuerySpec,
        params: tuple[Any, ...],
        *,
        fetch: str,
    ) -> Any:
        self.calls.append((spec, params, fetch))
        return self.result


class _CursorCM:
    def __init__(self, cursor: MagicMock) -> None:
        self._cursor = cursor

    def __enter__(self) -> MagicMock:
        return self._cursor

    def __exit__(self, *args: object) -> None:
        return None


def _ready_session(rows: list[Any]) -> tuple[DiagnosticSession, MagicMock, list[MagicMock]]:
    """A `DiagnosticSession` forced to READY over a mock connection."""
    conn = MagicMock()
    cursors: list[MagicMock] = []

    def cursor_factory(*args: object, **kwargs: object) -> _CursorCM:
        cur = MagicMock()
        result = rows.pop(0) if rows else None
        cur.fetchone.return_value = result
        cur.fetchall.return_value = result if isinstance(result, list) else []
        cursors.append(cur)
        return _CursorCM(cur)

    conn.cursor = MagicMock(side_effect=cursor_factory)
    session = DiagnosticSession(conn, SessionSafetyConfig())
    session._state = SessionState.READY
    return session, conn, cursors


# --- Rejection before any database work --------------------------------------


def test_unknown_query_id_executes_nothing() -> None:
    runner = _SpyRunner()
    with pytest.raises(UnknownQueryIdError):
        execute_allowlisted(runner, "impact.definitely_not_a_query", ())
    assert runner.calls == []


def test_unknown_query_id_never_reaches_the_cursor() -> None:
    session, conn, _ = _ready_session([])
    with pytest.raises(UnknownQueryIdError):
        execute_allowlisted(session, "impact.drop_everything", ())
    conn.cursor.assert_not_called()


def test_wrong_parameter_count_executes_nothing() -> None:
    runner = _SpyRunner()
    with pytest.raises(ParameterValidationError):
        execute_allowlisted(runner, "impact.fetch_relation", ())
    with pytest.raises(ParameterValidationError):
        execute_allowlisted(runner, "impact.fetch_relation", (1, 2))
    assert runner.calls == []


def test_wrong_parameter_type_executes_nothing() -> None:
    runner = _SpyRunner()
    with pytest.raises(ParameterValidationError):
        execute_allowlisted(runner, "impact.fetch_relation", ("16384",))
    with pytest.raises(ParameterValidationError):
        execute_allowlisted(runner, "impact.fetch_relation", (True,))
    with pytest.raises(ParameterValidationError):
        execute_allowlisted(runner, "impact.resolve_relation_candidates", ("public", "t"))
    assert runner.calls == []


def test_bad_parameters_never_reach_the_cursor() -> None:
    session, conn, _ = _ready_session([])
    with pytest.raises(ParameterValidationError):
        execute_allowlisted(session, "impact.fetch_relation", ("not-an-oid",))
    conn.cursor.assert_not_called()


def test_array_parameters_accept_list_or_tuple() -> None:
    runner = _SpyRunner(result=None)
    execute_allowlisted(runner, "impact.resolve_relation_candidates", (("public",), "t"))
    execute_allowlisted(runner, "impact.resolve_relation_candidates", (["public"], "t"))
    assert len(runner.calls) == 2


def test_unsupported_fetch_mode_executes_nothing() -> None:
    runner = _SpyRunner()
    with pytest.raises(ParameterValidationError):
        execute_allowlisted(runner, "impact.fetch_relation", (1,), fetch="many")  # type: ignore[arg-type]
    assert runner.calls == []


# --- The caller cannot choose the SQL ----------------------------------------


def test_public_seam_has_no_sql_parameter() -> None:
    parameters = set(inspect.signature(execute_allowlisted).parameters)
    assert parameters == {"session", "query_id", "params", "recorder", "fetch"}
    for forbidden in ("sql", "query", "statement", "text"):
        assert forbidden not in parameters


def test_seam_passes_the_registry_spec_verbatim() -> None:
    runner = _SpyRunner(result=None)
    execute_allowlisted(runner, "impact.fetch_relation", (16384,))
    spec, params, _ = runner.calls[0]
    assert spec is IMPACT_QUERY_REGISTRY["impact.fetch_relation"]
    assert params == (16384,)


def test_executed_sql_is_identical_to_registry_spec() -> None:
    session, conn, cursors = _ready_session([{"oid": 1, "nspname": "public", "relname": "t"}])
    execute_allowlisted(session, "impact.resolve_relation_candidates", (("public",), "t"))
    executed_sql, executed_params = cursors[0].execute.call_args[0]
    assert executed_sql == IMPACT_QUERY_REGISTRY["impact.resolve_relation_candidates"].sql
    assert executed_params == (("public",), "t")


# --- Recording reflects real invocation --------------------------------------


def test_recorder_event_matches_the_session_invocation() -> None:
    session, _, cursors = _ready_session([{"oid": 1, "nspname": "public", "relname": "t"}])
    events: list[QueryExecutionEvent] = []

    execute_allowlisted(
        session,
        "impact.resolve_relation_candidates",
        (("public",), "t"),
        recorder=events.append,
    )

    assert len(events) == 1
    event = events[0]
    executed_sql, executed_params = cursors[0].execute.call_args[0]
    assert event.query_id == "impact.resolve_relation_candidates"
    assert event.sql_text == executed_sql
    assert event.bound_parameters == executed_params
    assert event.command_kind == "SELECT"


def test_no_event_is_recorded_when_the_session_call_fails() -> None:
    class _Failing:
        def _execute_allowlisted_query(
            self, spec: QuerySpec, params: tuple[Any, ...], *, fetch: str
        ) -> Any:
            raise RuntimeError("cursor exploded")

    events: list[QueryExecutionEvent] = []
    with pytest.raises(RuntimeError):
        execute_allowlisted(_Failing(), "impact.fetch_relation", (1,), recorder=events.append)
    assert events == []


# --- Decoding ----------------------------------------------------------------


def test_seam_decodes_rows_through_the_spec_row_model() -> None:
    runner = _SpyRunner(result={"oid": 1, "nspname": "public", "relname": "t"})
    row = execute_allowlisted(runner, "impact.resolve_relation_candidates", (("public",), "t"))
    assert row == RelationCandidateRow(oid=1, nspname="public", relname="t")


def test_seam_decodes_every_row_for_fetch_all() -> None:
    runner = _SpyRunner(
        result=[
            {"oid": 1, "nspname": "public", "relname": "a"},
            {"oid": 2, "nspname": "app", "relname": "b"},
        ]
    )
    rows = execute_allowlisted(
        runner, "impact.resolve_relation_candidates", (("public",), "a"), fetch="all"
    )
    assert rows == (
        RelationCandidateRow(oid=1, nspname="public", relname="a"),
        RelationCandidateRow(oid=2, nspname="app", relname="b"),
    )


def test_fetch_none_discards_the_result() -> None:
    runner = _SpyRunner(result={"oid": 1})
    assert execute_allowlisted(runner, "impact.begin_read_only_rr", (), fetch="none") is None


# --- SessionQueryExecutor adapter --------------------------------------------


def test_session_query_executor_satisfies_the_protocol() -> None:
    session, _, _ = _ready_session([])
    executor = session.as_query_executor()
    assert isinstance(executor, SessionQueryExecutor)
    assert isinstance(executor, QueryExecutor)


def test_session_query_executor_returns_validated_columns() -> None:
    core = {
        "oid": 16384,
        "nspname": "public",
        "relname": "t",
        "relkind": "r",
        "relpersistence": "p",
        "relispartition": False,
        "inherits_parents": [],
        "inherits_children": [],
    }
    session, _, _ = _ready_session([core])
    row = session.as_query_executor().fetch_one("impact.fetch_relation", (16384,))
    assert row is not None
    assert dict(row) == dict(core, inherits_parents=(), inherits_children=())
    assert set(row) == {field.name for field in RelationRow.__dataclass_fields__.values()}


def test_session_query_executor_records_through_the_seam() -> None:
    session, _, _ = _ready_session(
        [[{"castsource": 1, "casttarget": 2, "castfunc": 0, "castcontext": "i", "castmethod": "b"}]]
    )
    events: list[QueryExecutionEvent] = []
    rows = session.as_query_executor(recorder=events.append).fetch_all(
        "impact.fetch_pg_cast", (1, 2)
    )
    assert len(rows) == 1
    assert [event.query_id for event in events] == ["impact.fetch_pg_cast"]
    assert events[0].sql_text == IMPACT_QUERY_REGISTRY["impact.fetch_pg_cast"].sql


def test_session_rejects_allowlisted_queries_when_not_ready() -> None:
    from pginspect.exceptions import PginspectInternalError

    conn = MagicMock()
    session = DiagnosticSession(conn, SessionSafetyConfig())
    with pytest.raises(PginspectInternalError):
        execute_allowlisted(session, "impact.fetch_relation", (1,))
    conn.cursor.assert_not_called()


# --- Boundary: catalog/resolve cannot bypass the seam ------------------------


def _module_tree(name: str) -> ast.AST:
    return ast.parse((SRC_IMPACT / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("module", ["catalog.py", "resolve.py", "query_exec.py", "query_rows.py"])
def test_impact_modules_do_not_import_psycopg(module: str) -> None:
    for node in ast.walk(_module_tree(module)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.split(".")[0] == "psycopg"
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.split(".")[0] == "psycopg"


@pytest.mark.parametrize("module", ["catalog.py", "resolve.py"])
def test_catalog_and_resolve_never_touch_a_cursor(module: str) -> None:
    for node in ast.walk(_module_tree(module)):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"cursor", "execute", "fetchone", "fetchall", "connection"}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"_execute_allowlisted_query", "_fetch_one", "_fetch_all"}


@pytest.mark.parametrize("module", ["catalog.py", "resolve.py"])
def test_catalog_and_resolve_only_read_through_the_executor_protocol(module: str) -> None:
    called = {
        node.func.attr
        for node in ast.walk(_module_tree(module))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "executor"
    }
    assert called <= {"fetch_one", "fetch_all"}


def test_catalog_and_resolve_contain_no_sql_text() -> None:
    for module in ("catalog.py", "resolve.py"):
        source = (SRC_IMPACT / module).read_text(encoding="utf-8")
        assert "SELECT " not in source
        assert "FROM pg_" not in source
