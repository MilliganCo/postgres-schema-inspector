"""Unit tests for DiagnosticSession state machine (mocked connection)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import MagicMock

import pytest
from psycopg.errors import ConnectionFailure, InsufficientPrivilege, SyntaxError

from pginspect.config import SessionSafetyConfig
from pginspect.exceptions import PginspectInternalError, SessionSafetyError
from pginspect.models.enums import SessionSafetyMisconfigurationCategory
from pginspect.session import DiagnosticSession, SessionState


class _CursorCM:
    def __init__(self, cursor: MagicMock) -> None:
        self._cursor = cursor

    def __enter__(self) -> MagicMock:
        return self._cursor

    def __exit__(self, *args: object) -> None:
        return None


def _config() -> SessionSafetyConfig:
    return SessionSafetyConfig()


def _mock_conn(*, establish_ok: bool = True, verify_row: dict[str, Any] | None = None) -> MagicMock:
    conn = MagicMock()
    conn.pgconn.ssl_in_use = False

    @contextmanager
    def _txn(*, force_rollback: bool = False) -> Iterator[None]:
        assert force_rollback is True
        yield None

    conn.transaction = MagicMock(side_effect=_txn)

    establish_cur = MagicMock()
    verify_cur = MagicMock()

    if not establish_ok:
        establish_cur.execute.side_effect = InsufficientPrivilege("rejected")
    else:
        establish_cur.fetchone.return_value = (1, 1, 1, 1, 1)

    if verify_row is None:
        verify_row = {
            "default_transaction_read_only": True,
            "transaction_read_only": True,
            "statement_timeout_ms": 15000,
            "statement_timeout_unit": "ms",
            "lock_timeout_ms": 2000,
            "lock_timeout_unit": "ms",
            "idle_in_transaction_session_timeout_ms": 15000,
            "idle_in_transaction_session_timeout_unit": "ms",
            "application_name": "pginspect/0.1.0",
            "search_path_raw": "pg_catalog",
            "effective_search_path": ["pg_catalog"],
        }
    verify_cur.fetchone.return_value = verify_row

    cursors = [establish_cur, verify_cur]

    def cursor_factory(*args: object, **kwargs: object) -> _CursorCM:
        if not cursors:
            # subsequent fetch cursors
            cur = MagicMock()
            return _CursorCM(cur)
        return _CursorCM(cursors.pop(0))

    conn.cursor = MagicMock(side_effect=cursor_factory)
    conn._cursors_left = cursors  # type: ignore[attr-defined]
    return conn


def test_query_before_ready_raises_internal() -> None:
    session = DiagnosticSession(MagicMock(), _config())
    assert session.state is SessionState.NEW
    with pytest.raises(PginspectInternalError, match="before READY"):
        session._fetch_one("SELECT 1")


def test_double_enter_raises_internal() -> None:
    conn = _mock_conn()
    session = DiagnosticSession(conn, _config())
    with session:
        assert session.state is SessionState.READY
        with pytest.raises(PginspectInternalError, match="entered twice"):
            session.__enter__()


def test_after_sql_error_session_is_failed_and_rejects_further_queries() -> None:
    conn = _mock_conn()
    with DiagnosticSession(conn, _config()) as session:
        assert session.state is SessionState.READY

        # Next cursor used by _fetch_one raises
        fail_cur = MagicMock()
        fail_cur.execute.side_effect = ConnectionFailure("broken")
        conn.cursor = MagicMock(return_value=_CursorCM(fail_cur))

        with pytest.raises(Exception):
            session._fetch_one("SELECT 1")
        assert session.state is SessionState.FAILED

        with pytest.raises(PginspectInternalError, match="FAILED"):
            session._fetch_one("SELECT 2")

    assert session.state is SessionState.CLOSED


def test_set_rejected_maps_to_session_safety_error() -> None:
    conn = _mock_conn(establish_ok=False)
    session = DiagnosticSession(conn, _config())
    with pytest.raises(SessionSafetyError) as exc_info:
        session.__enter__()
    assert exc_info.value.category is SessionSafetyMisconfigurationCategory.SET_REJECTED
    assert exc_info.value.observed is None
    assert session.state is SessionState.FAILED


def test_verification_mismatch_raises_session_safety_error() -> None:
    bad_row = {
        "default_transaction_read_only": False,
        "transaction_read_only": True,
        "statement_timeout_ms": 15000,
        "statement_timeout_unit": "ms",
        "lock_timeout_ms": 2000,
        "lock_timeout_unit": "ms",
        "idle_in_transaction_session_timeout_ms": 15000,
        "idle_in_transaction_session_timeout_unit": "ms",
        "application_name": "custom-app",
        "search_path_raw": "pg_catalog",
        "effective_search_path": ["pg_catalog"],
    }
    conn = _mock_conn(verify_row=bad_row)
    session = DiagnosticSession(conn, _config())
    with pytest.raises(SessionSafetyError) as exc_info:
        session.__enter__()
    assert exc_info.value.category is SessionSafetyMisconfigurationCategory.VERIFICATION_MISMATCH
    assert exc_info.value.observed is not None
    assert exc_info.value.observed.default_transaction_read_only is False


def test_verify_programming_error_maps_to_internal() -> None:
    conn = _mock_conn()
    # Replace verify cursor behavior: first cursor establish ok, second raises SyntaxError
    establish_cur = MagicMock()
    establish_cur.fetchone.return_value = (1,)
    verify_cur = MagicMock()
    verify_cur.execute.side_effect = SyntaxError("bad sql")
    queue = [establish_cur, verify_cur]
    conn.cursor = MagicMock(side_effect=lambda *a, **k: _CursorCM(queue.pop(0)))

    session = DiagnosticSession(conn, _config())
    with pytest.raises(PginspectInternalError):
        session.__enter__()
    assert session.state is SessionState.FAILED


def test_force_rollback_transaction_used() -> None:
    conn = _mock_conn()
    with DiagnosticSession(conn, _config()) as session:
        assert session.state is SessionState.READY
    conn.transaction.assert_called()
    # force_rollback must have been requested
    _, kwargs = conn.transaction.call_args
    assert kwargs.get("force_rollback") is True


def test_transport_metadata_reads_ssl_in_use() -> None:
    conn = _mock_conn()
    conn.pgconn.ssl_in_use = True
    with DiagnosticSession(conn, _config()) as session:
        meta = session.transport_metadata()
    assert meta.tls_used is True


def test_query_after_closed_raises_internal() -> None:
    conn = _mock_conn()
    with DiagnosticSession(conn, _config()) as session:
        pass
    assert session.state is SessionState.CLOSED
    with pytest.raises(PginspectInternalError, match="CLOSED"):
        session._fetch_one("SELECT 1")
