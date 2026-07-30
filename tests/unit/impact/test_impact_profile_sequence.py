"""Unit tests for `DiagnosticSession.establish_impact_profile` timeline (mocked)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from pginspect.config import SessionSafetyConfig
from pginspect.exceptions import PginspectInternalError
from pginspect.session import DiagnosticSession, ImpactSessionState

_RESOLUTION_ROW: dict[str, Any] = {
    "database": "app",
    "role": "app_role",
    "session_user": "app_role",
    "current_schema": "public",
    "current_schemas_user": ["public"],
    "current_schemas_with_implicit": ["public", "pg_catalog"],
    "search_path_raw": "public",
    "max_identifier_length_bytes": 63,
}

_VERIFY_SAFETY_ROW: dict[str, Any] = {
    "transaction_read_only": True,
    "transaction_isolation": "repeatable read",
    "search_path_raw": "pg_catalog",
    "effective_search_path": ["pg_catalog"],
    "statement_timeout_ms": 15000,
    "lock_timeout_ms": 2000,
    "idle_in_transaction_session_timeout_ms": 15000,
}

_PREFLIGHT_ROW: dict[str, Any] = {
    "server_version": "16.4",
    "server_version_num": 160004,
    "standard_conforming_strings": "on",
    "transaction_read_only": "on",
    "transaction_isolation": "repeatable read",
    "server_encoding": "UTF8",
    "client_encoding": "UTF8",
    "in_recovery": False,
    "keyword_categories": {"select": "R", "table": "R"},
}


@dataclass
class _RecordedCall:
    query_id: str
    sql_text: str
    params: tuple[object, ...]
    command_kind: str


class _FakeSessionRecorder:
    """Wraps a `DiagnosticSession` and captures the executed query timeline."""

    def __init__(self, session: DiagnosticSession) -> None:
        self._session = session
        self.calls: list[_RecordedCall] = []

    def _record(
        self,
        query_id: str,
        sql_text: str,
        params: tuple[object, ...],
        command_kind: str,
    ) -> None:
        self.calls.append(_RecordedCall(query_id, sql_text, params, command_kind))

    def establish_impact_profile(self) -> ImpactSessionState:
        return self._session.establish_impact_profile(recorder=self._record)

    @property
    def query_ids(self) -> list[str]:
        return [call.query_id for call in self.calls]

    @property
    def command_kinds(self) -> list[str]:
        return [call.command_kind for call in self.calls]

    @property
    def first_select_query_id(self) -> str | None:
        for call in self.calls:
            if call.command_kind == "SELECT":
                return call.query_id
        return None


class _CursorCM:
    def __init__(self, cursor: MagicMock) -> None:
        self._cursor = cursor

    def __enter__(self) -> MagicMock:
        return self._cursor

    def __exit__(self, *args: object) -> None:
        return None


def _mock_impact_conn() -> MagicMock:
    conn = MagicMock()

    fetch_results: list[Any] = [
        None,  # impact.begin_read_only_rr: BEGIN, no fetch
        (None, None, None),  # impact.set_timeouts: SELECT, discarded
        _RESOLUTION_ROW,  # impact.capture_resolution_context
        None,  # impact.harden_search_path: SET, no fetch
        _VERIFY_SAFETY_ROW,  # impact.verify_safety
        _PREFLIGHT_ROW,  # impact.preflight_reads
    ]

    def cursor_factory(*args: object, **kwargs: object) -> _CursorCM:
        cur = MagicMock()
        cur.fetchone.return_value = fetch_results.pop(0)
        return _CursorCM(cur)

    conn.cursor = MagicMock(side_effect=cursor_factory)
    return conn


@pytest.fixture
def fake_session_recorder() -> _FakeSessionRecorder:
    session = DiagnosticSession(_mock_impact_conn(), SessionSafetyConfig())
    return _FakeSessionRecorder(session)


def test_impact_profile_query_id_order(fake_session_recorder: _FakeSessionRecorder) -> None:
    state = fake_session_recorder.establish_impact_profile()
    assert fake_session_recorder.query_ids == [
        "impact.begin_read_only_rr",
        "impact.set_timeouts",
        "impact.capture_resolution_context",
        "impact.harden_search_path",
        "impact.verify_safety",
        "impact.preflight_reads",
    ]
    assert fake_session_recorder.command_kinds == [
        "BEGIN",
        "SELECT",
        "SELECT",
        "SET",
        "SELECT",
        "SELECT",
    ]
    assert fake_session_recorder.first_select_query_id == "impact.set_timeouts"
    assert state.catalog_snapshot_at.tzinfo is not None


def test_begin_precedes_any_select(fake_session_recorder: _FakeSessionRecorder) -> None:
    fake_session_recorder.establish_impact_profile()
    first_call = fake_session_recorder.calls[0]
    assert first_call.query_id == "impact.begin_read_only_rr"
    assert first_call.command_kind == "BEGIN"


def test_capture_resolution_context_precedes_harden(
    fake_session_recorder: _FakeSessionRecorder,
) -> None:
    fake_session_recorder.establish_impact_profile()
    capture_index = fake_session_recorder.query_ids.index("impact.capture_resolution_context")
    harden_index = fake_session_recorder.query_ids.index("impact.harden_search_path")
    assert capture_index < harden_index


def test_set_timeouts_uses_bound_string_parameters(
    fake_session_recorder: _FakeSessionRecorder,
) -> None:
    fake_session_recorder.establish_impact_profile()
    set_timeouts_call = next(
        call for call in fake_session_recorder.calls if call.query_id == "impact.set_timeouts"
    )
    assert set_timeouts_call.params == ("15000ms", "2000ms", "15000ms")
    assert "set_config" in set_timeouts_call.sql_text
    assert "%s" in set_timeouts_call.sql_text


def test_impact_profile_returns_resolution_and_connection_context(
    fake_session_recorder: _FakeSessionRecorder,
) -> None:
    state = fake_session_recorder.establish_impact_profile()

    resolution_context = state.resolution_context
    assert resolution_context.database == "app"
    assert resolution_context.role == "app_role"
    assert resolution_context.session_user == "app_role"
    assert resolution_context.current_schema == "public"
    assert resolution_context.current_schemas_user == ("public",)
    assert resolution_context.current_schemas_with_implicit == ("public", "pg_catalog")
    assert resolution_context.search_path_raw == "public"
    assert resolution_context.max_identifier_length_bytes == 63
    assert resolution_context.server_major == 16
    assert resolution_context.server_version_num == 160004
    assert resolution_context.keyword_categories == {"select": "R", "table": "R"}

    connection_context = state.connection_context
    assert connection_context.server_version == "16.4"
    assert connection_context.server_version_num == 160004
    assert connection_context.server_major == 16
    assert connection_context.database == "app"
    assert connection_context.role == "app_role"
    assert connection_context.current_schema == "public"
    assert connection_context.standard_conforming_strings == "on"
    assert connection_context.transaction_read_only == "on"
    assert connection_context.transaction_isolation == "repeatable read"
    assert connection_context.server_encoding == "UTF8"
    assert connection_context.client_encoding == "UTF8"
    assert connection_context.in_recovery is False
    assert connection_context.max_identifier_length == 63


def test_establish_impact_profile_cannot_be_called_twice() -> None:
    session = DiagnosticSession(_mock_impact_conn(), SessionSafetyConfig())
    session.establish_impact_profile()
    with pytest.raises(PginspectInternalError, match="cannot be called twice"):
        session.establish_impact_profile()


def test_establish_impact_profile_works_without_recorder() -> None:
    session = DiagnosticSession(_mock_impact_conn(), SessionSafetyConfig())
    state = session.establish_impact_profile()
    assert isinstance(state, ImpactSessionState)
