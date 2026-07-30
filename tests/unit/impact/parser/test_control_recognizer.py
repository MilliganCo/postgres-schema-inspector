"""Tests for the exact control-statement recognizer (design section 1.5)."""

from __future__ import annotations

import pytest

from pginspect.impact.parser.ast import Token
from pginspect.impact.parser.control import is_control_statement
from pginspect.impact.parser.split import split_statements
from pginspect.impact.parser.tokens import tokenize


def _tokens_for(sql: str) -> tuple[Token, ...]:
    (raw,) = split_statements(sql)
    return tokenize(raw)


@pytest.mark.parametrize(
    "sql",
    [
        "BEGIN;",
        "begin;",
        "BEGIN WORK;",
        "Begin Work;",
        "BEGIN TRANSACTION;",
        "START TRANSACTION;",
        "start transaction;",
        "COMMIT;",
        "COMMIT WORK;",
        "COMMIT TRANSACTION;",
        "END;",
        "END WORK;",
        "END TRANSACTION;",
    ],
)
def test_recognizes_exact_control_forms(sql: str) -> None:
    assert is_control_statement(_tokens_for(sql)) is True


@pytest.mark.parametrize(
    "sql",
    [
        "BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;",
        "COMMIT AND CHAIN;",
        "ROLLBACK;",
        "SAVEPOINT sp1;",
        "RELEASE SAVEPOINT sp1;",
        "SET search_path = public;",
        "RESET search_path;",
        "LOCK TABLE t;",
        "ALTER TABLE t ADD COLUMN a int;",
        "START;",
    ],
)
def test_rejects_non_exact_or_unrecognized_forms(sql: str) -> None:
    assert is_control_statement(_tokens_for(sql)) is False


def test_control_recognition_ignores_surrounding_comments() -> None:
    tokens = _tokens_for("BEGIN /* note */ WORK;")
    assert is_control_statement(tokens) is True


def test_empty_token_sequence_is_not_control() -> None:
    assert is_control_statement(()) is False
