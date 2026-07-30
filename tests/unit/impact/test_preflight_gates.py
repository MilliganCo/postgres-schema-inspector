"""Unit tests for pure impact preflight gate evaluation (no psycopg, no DB)."""

from __future__ import annotations

import pytest

from pginspect.impact.models.result import ImpactConnectionContext
from pginspect.impact.preflight import (
    PreflightGateFailure,
    evaluate_preflight_gates,
)


def _context(**overrides: object) -> ImpactConnectionContext:
    base: dict[str, object] = {
        "server_version": "16.4",
        "server_version_num": 160004,
        "server_major": 16,
        "database": "app",
        "role": "app_role",
        "session_user": "app_role",
        "current_schema": "public",
        "search_path_raw": "pg_catalog",
        "standard_conforming_strings": "on",
        "server_encoding": "UTF8",
        "client_encoding": "UTF8",
        "transaction_isolation": "repeatable read",
        "transaction_read_only": "on",
        "in_recovery": False,
        "max_identifier_length": 63,
    }
    base.update(overrides)
    return ImpactConnectionContext(**base)  # type: ignore[arg-type]


def test_fully_supported_context_is_complete() -> None:
    evaluation = evaluate_preflight_gates(_context())
    assert evaluation.incomplete is False
    assert evaluation.failures == ()


@pytest.mark.parametrize("major", [14, 15, 16, 17, 18])
def test_all_supported_majors_pass(major: int) -> None:
    version_num = major * 10_000 + 4
    evaluation = evaluate_preflight_gates(
        _context(server_major=major, server_version_num=version_num)
    )
    assert evaluation.incomplete is False


@pytest.mark.parametrize("major", [9, 10, 11, 12, 13, 19, 20])
def test_unsupported_major_is_incomplete(major: int) -> None:
    evaluation = evaluate_preflight_gates(_context(server_major=major))
    assert evaluation.incomplete is True
    assert any(f.check_id == "server_major" for f in evaluation.failures)


def test_standard_conforming_strings_off_is_incomplete() -> None:
    evaluation = evaluate_preflight_gates(_context(standard_conforming_strings="off"))
    assert evaluation.incomplete is True
    assert any(f.check_id == "standard_conforming_strings" for f in evaluation.failures)


def test_transaction_not_read_only_is_incomplete() -> None:
    evaluation = evaluate_preflight_gates(_context(transaction_read_only="off"))
    assert evaluation.incomplete is True
    assert any(f.check_id == "transaction_read_only" for f in evaluation.failures)


def test_transaction_isolation_not_repeatable_read_is_incomplete() -> None:
    evaluation = evaluate_preflight_gates(_context(transaction_isolation="read committed"))
    assert evaluation.incomplete is True
    assert any(f.check_id == "transaction_isolation" for f in evaluation.failures)


@pytest.mark.parametrize(
    ("server_encoding", "client_encoding"),
    [("LATIN1", "UTF8"), ("UTF8", "LATIN1"), ("LATIN1", "LATIN1")],
)
def test_non_utf8_encoding_is_incomplete(server_encoding: str, client_encoding: str) -> None:
    evaluation = evaluate_preflight_gates(
        _context(server_encoding=server_encoding, client_encoding=client_encoding)
    )
    assert evaluation.incomplete is True
    assert any(f.check_id == "encoding" for f in evaluation.failures)


def test_multiple_failures_are_all_reported() -> None:
    evaluation = evaluate_preflight_gates(
        _context(
            server_major=13,
            standard_conforming_strings="off",
            transaction_read_only="off",
            transaction_isolation="read committed",
            server_encoding="LATIN1",
            client_encoding="LATIN1",
        )
    )
    assert evaluation.incomplete is True
    check_ids = {f.check_id for f in evaluation.failures}
    assert check_ids == {
        "server_major",
        "standard_conforming_strings",
        "transaction_read_only",
        "transaction_isolation",
        "encoding",
    }


def test_preflight_gate_failure_carries_detail() -> None:
    evaluation = evaluate_preflight_gates(_context(server_major=99))
    failure = evaluation.failures[0]
    assert isinstance(failure, PreflightGateFailure)
    assert "99" in failure.detail
