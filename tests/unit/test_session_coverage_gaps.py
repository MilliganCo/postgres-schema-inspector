"""Additional DiagnosticSession unit coverage for error mapping edges."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest
from psycopg.errors import ConnectionFailure, QueryCanceled

from pginspect.config import SessionSafetyConfig
from pginspect.exceptions import (
    ConnectFailedError,
    ConnectNetworkError,
    PginspectInternalError,
)
from pginspect.models.enums import ExecutionErrorCode
from pginspect.session import (
    DiagnosticSession,
    SessionState,
    _classify_application_name,
    observe_transport_metadata,
)


class _CursorCM:
    def __init__(self, cursor: MagicMock) -> None:
        self._cursor = cursor

    def __enter__(self) -> MagicMock:
        return self._cursor

    def __exit__(self, *args: object) -> None:
        return None


def _config() -> SessionSafetyConfig:
    return SessionSafetyConfig()


def _ok_verify_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
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
    row.update(overrides)
    return row


def _mock_conn_with_cursors(cursors: list[MagicMock]) -> MagicMock:
    conn = MagicMock()
    conn.pgconn.ssl_in_use = False

    @contextmanager
    def _txn(*, force_rollback: bool = False) -> Iterator[None]:
        assert force_rollback is True
        yield None

    conn.transaction = MagicMock(side_effect=_txn)
    queue = list(cursors)

    def cursor_factory(*args: object, **kwargs: object) -> _CursorCM:
        if not queue:
            return _CursorCM(MagicMock())
        return _CursorCM(queue.pop(0))

    conn.cursor = MagicMock(side_effect=cursor_factory)
    return conn


def test_observe_transport_metadata_none_pgconn() -> None:
    conn = MagicMock()
    conn.pgconn = None
    assert observe_transport_metadata(conn).tls_used is None


def test_observe_transport_metadata_exception() -> None:
    conn = MagicMock()
    type(conn).pgconn = property(lambda self: (_ for _ in ()).throw(RuntimeError("gone")))
    assert observe_transport_metadata(conn).tls_used is None


def test_classify_application_name_variants() -> None:
    assert _classify_application_name("") == ("empty", None)
    kind, value = _classify_application_name("pginspect/9.9.9")
    assert kind == "pginspect_owned"
    assert value == "pginspect/9.9.9"
    assert _classify_application_name("other-app") == ("custom", None)


def test_verification_evidence_unavailable_before_enter() -> None:
    session = DiagnosticSession(MagicMock(), _config())
    with pytest.raises(PginspectInternalError, match="unavailable"):
        _ = session.verification_evidence


def test_establish_08_sqlstate_maps_to_network() -> None:
    establish = MagicMock()
    fail = ConnectionFailure("broken")
    fail.sqlstate = "08006"  # type: ignore[attr-defined]
    establish.execute.side_effect = fail
    conn = _mock_conn_with_cursors([establish])
    session = DiagnosticSession(conn, _config())
    with pytest.raises(ConnectNetworkError) as exc_info:
        session.__enter__()
    assert exc_info.value.code is ExecutionErrorCode.NETWORK_UNREACHABLE
    assert session.state is SessionState.FAILED


def test_establish_57014_maps_to_operational() -> None:
    establish = MagicMock()
    fail = QueryCanceled("cancel")
    fail.sqlstate = "57014"  # type: ignore[attr-defined]
    establish.execute.side_effect = fail
    conn = _mock_conn_with_cursors([establish])
    session = DiagnosticSession(conn, _config())
    with pytest.raises(ConnectFailedError) as exc_info:
        session.__enter__()
    assert exc_info.value.code is ExecutionErrorCode.OPERATIONAL_FAILURE


def test_establish_operational_without_sqlstate() -> None:
    establish = MagicMock()
    fail = ConnectionFailure("broken")
    fail.sqlstate = None  # type: ignore[attr-defined]
    establish.execute.side_effect = fail
    conn = _mock_conn_with_cursors([establish])
    session = DiagnosticSession(conn, _config())
    with pytest.raises(ConnectFailedError) as exc_info:
        session.__enter__()
    assert exc_info.value.code is ExecutionErrorCode.OPERATIONAL_FAILURE


def test_unexpected_exception_during_enter_maps_internal() -> None:
    establish = MagicMock()
    establish.execute.side_effect = RuntimeError("weird")
    conn = _mock_conn_with_cursors([establish])
    session = DiagnosticSession(conn, _config())
    with pytest.raises(PginspectInternalError, match="unexpected error"):
        session.__enter__()
    assert session.state is SessionState.FAILED


def test_verify_none_row_raises_internal() -> None:
    establish = MagicMock()
    establish.fetchone.return_value = (1,)
    verify = MagicMock()
    verify.fetchone.return_value = None
    conn = _mock_conn_with_cursors([establish, verify])
    session = DiagnosticSession(conn, _config())
    with pytest.raises(PginspectInternalError, match="no row"):
        session.__enter__()


def test_verify_bad_shape_raises_internal() -> None:
    establish = MagicMock()
    establish.fetchone.return_value = (1,)
    verify = MagicMock()
    verify.fetchone.return_value = {"default_transaction_read_only": True}
    conn = _mock_conn_with_cursors([establish, verify])
    session = DiagnosticSession(conn, _config())
    with pytest.raises(PginspectInternalError, match="unexpected shape"):
        session.__enter__()


def test_verify_bad_effective_search_path_type() -> None:
    establish = MagicMock()
    establish.fetchone.return_value = (1,)
    verify = MagicMock()
    verify.fetchone.return_value = _ok_verify_row(effective_search_path="pg_catalog")
    conn = _mock_conn_with_cursors([establish, verify])
    session = DiagnosticSession(conn, _config())
    with pytest.raises(PginspectInternalError, match="effective_search_path"):
        session.__enter__()


def test_close_stack_swallows_close_errors() -> None:
    establish = MagicMock()
    establish.fetchone.return_value = (1,)
    verify = MagicMock()
    verify.fetchone.return_value = _ok_verify_row()
    conn = _mock_conn_with_cursors([establish, verify])

    stack = MagicMock()
    stack.close.side_effect = RuntimeError("close failed")
    with patch("pginspect.session.ExitStack", return_value=stack):
        session = DiagnosticSession(conn, _config())
        # Force READY path then exit; close errors swallowed.
        session._stack = stack
        session._state = SessionState.READY
        session._entered = True
        session.__exit__(None, None, None)
    assert session.state is SessionState.CLOSED


def test_exit_marks_failed_on_psycopg_error() -> None:
    establish = MagicMock()
    establish.fetchone.return_value = (1,)
    verify = MagicMock()
    verify.fetchone.return_value = _ok_verify_row()
    conn = _mock_conn_with_cursors([establish, verify])
    with DiagnosticSession(conn, _config()) as session:
        assert session.state is SessionState.READY
        session.__exit__(ConnectionFailure, ConnectionFailure("x"), None)
    assert session.state is SessionState.CLOSED


def test_fetch_one_none_row_raises() -> None:
    establish = MagicMock()
    establish.fetchone.return_value = (1,)
    verify = MagicMock()
    verify.fetchone.return_value = _ok_verify_row()
    fetch = MagicMock()
    fetch.fetchone.return_value = None
    conn = _mock_conn_with_cursors([establish, verify, fetch])
    with DiagnosticSession(conn, _config()) as session:
        with pytest.raises(PginspectInternalError, match="query returned no row"):
            session._fetch_one("SELECT 1")


def test_fetch_all_maps_psycopg_error() -> None:
    establish = MagicMock()
    establish.fetchone.return_value = (1,)
    verify = MagicMock()
    verify.fetchone.return_value = _ok_verify_row()
    fetch = MagicMock()
    fetch.execute.side_effect = ConnectionFailure("gone")
    conn = _mock_conn_with_cursors([establish, verify, fetch])
    with DiagnosticSession(conn, _config()) as session:
        with pytest.raises(Exception):
            session._fetch_all("SELECT 1")
        assert session.state is SessionState.FAILED


def test_fetch_all_success() -> None:
    establish = MagicMock()
    establish.fetchone.return_value = (1,)
    verify = MagicMock()
    verify.fetchone.return_value = _ok_verify_row()
    fetch = MagicMock()
    fetch.fetchall.return_value = [{"a": 1}, {"a": 2}]
    conn = _mock_conn_with_cursors([establish, verify, fetch])
    with DiagnosticSession(conn, _config()) as session:
        rows = session._fetch_all("SELECT 1")
    assert list(rows) == [{"a": 1}, {"a": 2}]


def test_empty_application_name_kind() -> None:
    establish = MagicMock()
    establish.fetchone.return_value = (1,)
    verify = MagicMock()
    verify.fetchone.return_value = _ok_verify_row(application_name="")
    conn = _mock_conn_with_cursors([establish, verify])
    with DiagnosticSession(conn, _config()) as session:
        assert session.verification_evidence.application_name_kind == "empty"
