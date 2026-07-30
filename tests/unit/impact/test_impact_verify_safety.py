"""`impact.verify_safety` must be enforced, fail closed, and gate preflight.

The hardened impact session is only trustworthy if the post-harden
verification row is actually compared against `SessionSafetyConfig`. Each
mismatch category below must abort the timeline with the Foundation
`SessionSafetyError` / `VERIFICATION_MISMATCH` mechanism *before*
`impact.preflight_reads` is issued.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pginspect.config import SessionSafetyConfig
from pginspect.exceptions import PginspectInternalError, SessionSafetyError
from pginspect.models.enums import SessionSafetyMisconfigurationCategory
from pginspect.session import DiagnosticSession, SessionState

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

_PREFLIGHT_ROW: dict[str, Any] = {
    "server_version": "16.4",
    "server_version_num": 160004,
    "standard_conforming_strings": "on",
    "transaction_read_only": "on",
    "transaction_isolation": "repeatable read",
    "server_encoding": "UTF8",
    "client_encoding": "UTF8",
    "in_recovery": False,
    "keyword_categories": {"select": "R"},
}

_HARDENED_VERIFY_ROW: dict[str, Any] = {
    "transaction_read_only": True,
    "transaction_isolation": "repeatable read",
    "search_path_raw": "pg_catalog",
    "effective_search_path": ["pg_catalog"],
    "statement_timeout_ms": 15000,
    "lock_timeout_ms": 2000,
    "idle_in_transaction_session_timeout_ms": 15000,
}


class _CursorCM:
    def __init__(self, cursor: MagicMock) -> None:
        self._cursor = cursor

    def __enter__(self) -> MagicMock:
        return self._cursor

    def __exit__(self, *args: object) -> None:
        return None


def _mock_conn(verify_row: dict[str, Any] | None) -> MagicMock:
    conn = MagicMock()
    fetch_results: list[Any] = [
        None,  # impact.begin_read_only_rr
        (None, None, None),  # impact.set_timeouts
        _RESOLUTION_ROW,  # impact.capture_resolution_context
        None,  # impact.harden_search_path
        verify_row,  # impact.verify_safety
        _PREFLIGHT_ROW,  # impact.preflight_reads
    ]

    def cursor_factory(*args: object, **kwargs: object) -> _CursorCM:
        cur = MagicMock()
        cur.fetchone.return_value = fetch_results.pop(0)
        return _CursorCM(cur)

    conn.cursor = MagicMock(side_effect=cursor_factory)
    return conn


class _Timeline:
    def __init__(self) -> None:
        self.query_ids: list[str] = []

    def record(
        self,
        query_id: str,
        sql_text: str,
        params: tuple[object, ...],
        command_kind: str,
    ) -> None:
        self.query_ids.append(query_id)


def _verify_row(**overrides: Any) -> dict[str, Any]:
    row = dict(_HARDENED_VERIFY_ROW)
    row.update(overrides)
    return row


_MISMATCHES: list[tuple[str, dict[str, Any]]] = [
    ("transaction_read_only", {"transaction_read_only": False}),
    ("transaction_isolation", {"transaction_isolation": "read committed"}),
    ("effective_search_path", {"effective_search_path": ["public", "pg_catalog"]}),
    ("search_path_raw", {"search_path_raw": "public"}),
    ("statement_timeout_ms", {"statement_timeout_ms": 60000}),
    ("lock_timeout_ms", {"lock_timeout_ms": 1}),
    ("idle_in_transaction_session_timeout_ms", {"idle_in_transaction_session_timeout_ms": 1}),
]


@pytest.mark.parametrize(
    ("category", "override"),
    _MISMATCHES,
    ids=[name for name, _ in _MISMATCHES],
)
def test_verify_safety_mismatch_fails_closed_before_preflight(
    category: str, override: dict[str, Any]
) -> None:
    timeline = _Timeline()
    session = DiagnosticSession(_mock_conn(_verify_row(**override)), SessionSafetyConfig())

    with pytest.raises(SessionSafetyError) as excinfo:
        session.establish_impact_profile(recorder=timeline.record)

    assert excinfo.value.category is SessionSafetyMisconfigurationCategory.VERIFICATION_MISMATCH
    assert "impact.verify_safety" in timeline.query_ids
    assert "impact.preflight_reads" not in timeline.query_ids
    assert session.state is SessionState.FAILED


@pytest.mark.parametrize(
    ("category", "override"),
    _MISMATCHES,
    ids=[name for name, _ in _MISMATCHES],
)
def test_verify_safety_mismatch_returns_no_session_state(
    category: str, override: dict[str, Any]
) -> None:
    session = DiagnosticSession(_mock_conn(_verify_row(**override)), SessionSafetyConfig())
    with pytest.raises(SessionSafetyError):
        session.establish_impact_profile()


def test_verify_safety_mismatch_reports_observed_state() -> None:
    session = DiagnosticSession(
        _mock_conn(_verify_row(transaction_read_only=False)), SessionSafetyConfig()
    )
    with pytest.raises(SessionSafetyError) as excinfo:
        session.establish_impact_profile()

    observed = excinfo.value.observed
    assert observed is not None
    assert observed.transaction_read_only is False
    assert observed.search_path == ("pg_catalog",)
    assert excinfo.value.expected.statement_timeout_ms == 15000


def test_verify_safety_honours_non_default_config() -> None:
    config = SessionSafetyConfig(
        statement_timeout_ms=9000,
        lock_timeout_ms=1000,
        idle_in_transaction_session_timeout_ms=9000,
    )
    timeline = _Timeline()
    session = DiagnosticSession(_mock_conn(_HARDENED_VERIFY_ROW), config)

    with pytest.raises(SessionSafetyError):
        session.establish_impact_profile(recorder=timeline.record)
    assert "impact.preflight_reads" not in timeline.query_ids


def test_verify_safety_accepts_hardened_row_and_runs_preflight() -> None:
    timeline = _Timeline()
    session = DiagnosticSession(_mock_conn(_HARDENED_VERIFY_ROW), SessionSafetyConfig())

    state = session.establish_impact_profile(recorder=timeline.record)

    assert timeline.query_ids[-1] == "impact.preflight_reads"
    assert session.state is SessionState.READY
    assert state.connection_context.server_version_num == 160004


def test_verify_safety_normalizes_isolation_text() -> None:
    session = DiagnosticSession(
        _mock_conn(_verify_row(transaction_isolation="REPEATABLE  READ")),
        SessionSafetyConfig(),
    )
    assert session.establish_impact_profile() is not None


def test_verify_safety_missing_row_is_internal_error() -> None:
    timeline = _Timeline()
    session = DiagnosticSession(_mock_conn(None), SessionSafetyConfig())

    with pytest.raises(PginspectInternalError):
        session.establish_impact_profile(recorder=timeline.record)
    assert "impact.preflight_reads" not in timeline.query_ids
    assert session.state is SessionState.FAILED


def test_verify_safety_missing_field_is_internal_error() -> None:
    row = _verify_row()
    del row["statement_timeout_ms"]
    session = DiagnosticSession(_mock_conn(row), SessionSafetyConfig())

    with pytest.raises(PginspectInternalError):
        session.establish_impact_profile()
    assert session.state is SessionState.FAILED
