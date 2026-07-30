"""Tests for the lexical FSM statement splitter (design section 1.2)."""

from __future__ import annotations

import pytest

from pginspect.impact.input import LocalPhaseError
from pginspect.impact.parser.split import LexemeKind, split_statements


def test_splits_two_simple_statements() -> None:
    stmts = split_statements("SELECT 1; SELECT 2;")
    assert len(stmts) == 2


def test_semicolon_inside_single_quoted_string_does_not_split() -> None:
    stmts = split_statements("SELECT 'a;b';")
    assert len(stmts) == 1


def test_semicolon_inside_double_quoted_identifier_does_not_split() -> None:
    stmts = split_statements('SELECT "weird;name" FROM t;')
    assert len(stmts) == 1


def test_semicolon_inside_dollar_quote_does_not_split() -> None:
    stmts = split_statements("SELECT $tag$ a; b $tag$;")
    assert len(stmts) == 1


def test_semicolon_inside_line_comment_does_not_split() -> None:
    stmts = split_statements("SELECT 1; -- trailing ; comment\n")
    assert len(stmts) == 1


def test_semicolon_inside_block_comment_does_not_split() -> None:
    stmts = split_statements("SELECT 1 /* a; b */;")
    assert len(stmts) == 1


def test_empty_and_comment_only_segments_do_not_produce_statements() -> None:
    stmts = split_statements(";;\n-- just a comment\n;")
    assert stmts == ()


def test_trailing_statement_without_final_semicolon_is_kept() -> None:
    stmts = split_statements("SELECT 1")
    assert len(stmts) == 1


def test_backslash_outside_string_is_rejected() -> None:
    with pytest.raises(LocalPhaseError):
        split_statements("\\set foo bar\nSELECT 1;")


def test_backslash_inside_escape_string_is_not_rejected() -> None:
    stmts = split_statements(r"SELECT E'a\'b';")
    assert len(stmts) == 1


def test_unclosed_single_quote_string_is_rejected() -> None:
    with pytest.raises(LocalPhaseError):
        split_statements("SELECT 'unclosed;")


def test_unclosed_double_quoted_identifier_is_rejected() -> None:
    with pytest.raises(LocalPhaseError):
        split_statements('SELECT "unclosed;')


def test_unclosed_block_comment_is_rejected() -> None:
    with pytest.raises(LocalPhaseError):
        split_statements("SELECT 1 /* never closed")


def test_dollar_quote_unclosed_is_rejected() -> None:
    with pytest.raises(LocalPhaseError):
        split_statements("SELECT $tag$ body without closing tag")


def test_dollar_tag_mismatch_is_rejected() -> None:
    with pytest.raises(LocalPhaseError):
        split_statements("SELECT $tag1$ body $tag2$ trailing text")


def test_dollar_one_is_not_a_dollar_quote() -> None:
    (stmt,) = split_statements("SELECT $1;")
    kinds = [lex.kind for lex in stmt.lexemes if lex.kind is not LexemeKind.WHITESPACE]
    assert LexemeKind.PUNCTUATION in kinds
    assert LexemeKind.DOLLAR_LITERAL not in kinds


def test_nested_block_comment_depth_64_is_accepted() -> None:
    opens = "/*" * 64
    closes = "*/" * 64
    stmts = split_statements(f"SELECT 1 {opens} nested {closes};")
    assert len(stmts) == 1


def test_nested_block_comment_depth_65_is_rejected() -> None:
    opens = "/*" * 65
    with pytest.raises(LocalPhaseError):
        split_statements(f"SELECT 1 {opens} nested")


def test_statement_count_over_limit_is_rejected() -> None:
    text = "SELECT 1;" * 1001
    with pytest.raises(LocalPhaseError):
        split_statements(text, max_statements=1000)


def test_statement_count_at_limit_is_accepted() -> None:
    text = "SELECT 1;" * 1000
    stmts = split_statements(text, max_statements=1000)
    assert len(stmts) == 1000
