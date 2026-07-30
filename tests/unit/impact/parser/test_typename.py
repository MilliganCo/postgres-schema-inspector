"""Tests for `TypeName` parsing (design section 1b)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pginspect.impact.parser.ast import Token
from pginspect.impact.parser.grammar_alter import parse_type_name
from pginspect.impact.parser.split import split_statements
from pginspect.impact.parser.tokens import tokenize

_KEYWORDS_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "impact" / "keywords"
_MAJORS = [14, 15, 16, 17, 18]


def _keywords_for(major: int) -> dict[str, str]:
    return json.loads((_KEYWORDS_ROOT / f"pg{major}.json").read_text(encoding="utf-8"))


def _tokens_for(sql: str) -> tuple[Token, ...]:
    (raw,) = split_statements(sql)
    return tokenize(raw)


@pytest.mark.parametrize("major", _MAJORS)
def test_simple_unqualified_type_name(major: int) -> None:
    tokens = _tokens_for("integer")
    result = parse_type_name(tokens, 0, _keywords_for(major))
    assert result is not None
    type_name, idx = result
    assert idx == len(tokens)
    assert type_name.name.normalized == "integer"
    assert type_name.name.schema is None
    assert not type_name.name.is_multiword_builtin
    assert type_name.typmod == ()
    assert type_name.array_bounds == ()


@pytest.mark.parametrize("major", _MAJORS)
def test_schema_qualified_type_name(major: int) -> None:
    tokens = _tokens_for("myschema.mytype")
    type_name, idx = parse_type_name(tokens, 0, _keywords_for(major))  # type: ignore[misc]
    assert idx == len(tokens)
    assert type_name.name.normalized == "myschema.mytype"
    assert type_name.name.schema is not None
    assert type_name.name.schema.normalized_value == "myschema"


@pytest.mark.parametrize(
    ("sql", "canonical"),
    [
        ("double precision", "double precision"),
        ("character varying", "character varying"),
        ("bit varying", "bit varying"),
        ("character", "character"),
        ("char", "char"),
        ("varchar", "varchar"),
        ("national character varying", "national character varying"),
        ("national character", "national character"),
        ("national char", "national char"),
        ("time with time zone", "time with time zone"),
        ("time without time zone", "time without time zone"),
        ("timestamp with time zone", "timestamp with time zone"),
        ("timestamp without time zone", "timestamp without time zone"),
        ("interval", "interval"),
    ],
)
@pytest.mark.parametrize("major", _MAJORS)
def test_multiword_builtin_allowlist(sql: str, canonical: str, major: int) -> None:
    tokens = _tokens_for(sql)
    result = parse_type_name(tokens, 0, _keywords_for(major))
    assert result is not None
    type_name, idx = result
    assert idx == len(tokens)
    assert type_name.name.is_multiword_builtin
    assert type_name.name.normalized == canonical


def test_national_character_varying_prefers_longest_match() -> None:
    tokens = _tokens_for("national character varying")
    type_name, idx = parse_type_name(tokens, 0, _keywords_for(16))  # type: ignore[misc]
    assert idx == len(tokens)
    assert type_name.name.normalized == "national character varying"


def test_varchar_with_typmod() -> None:
    tokens = _tokens_for("varchar(20)")
    type_name, idx = parse_type_name(tokens, 0, _keywords_for(16))  # type: ignore[misc]
    assert idx == len(tokens)
    assert type_name.name.normalized == "varchar"
    assert len(type_name.typmod) == 1
    assert type_name.typmod[0].integer_value == 20


def test_numeric_with_two_typmod_args() -> None:
    tokens = _tokens_for("numeric(10, 2)")
    type_name, idx = parse_type_name(tokens, 0, _keywords_for(16))  # type: ignore[misc]
    assert idx == len(tokens)
    assert [arg.integer_value for arg in type_name.typmod] == [10, 2]


def test_interval_with_typmod() -> None:
    tokens = _tokens_for("interval(6)")
    type_name, idx = parse_type_name(tokens, 0, _keywords_for(16))  # type: ignore[misc]
    assert idx == len(tokens)
    assert type_name.name.normalized == "interval"
    assert type_name.typmod[0].integer_value == 6


def test_interval_field_syntax_is_unsupported() -> None:
    # "interval" matches the builtin, but "year to month" are leftover
    # top-level tokens the TypeName grammar does not consume; the caller
    # (grammar_alter family parsers) rejects the resulting trailing tokens.
    tokens = _tokens_for("interval year to month")
    type_name, idx = parse_type_name(tokens, 0, _keywords_for(16))  # type: ignore[misc]
    assert type_name.name.normalized == "interval"
    assert idx < len(tokens)


def test_empty_typmod_parens_is_rejected() -> None:
    tokens = _tokens_for("varchar()")
    result = parse_type_name(tokens, 0, _keywords_for(16))
    assert result is None


def test_array_bounds_unbound() -> None:
    tokens = _tokens_for("integer[]")
    type_name, idx = parse_type_name(tokens, 0, _keywords_for(16))  # type: ignore[misc]
    assert idx == len(tokens)
    assert len(type_name.array_bounds) == 1
    assert type_name.array_bounds[0].unbound is True
    assert type_name.array_bounds[0].length is None


def test_array_bounds_with_length() -> None:
    tokens = _tokens_for("integer[3]")
    type_name, idx = parse_type_name(tokens, 0, _keywords_for(16))  # type: ignore[misc]
    assert idx == len(tokens)
    assert type_name.array_bounds[0].unbound is False
    assert type_name.array_bounds[0].length == 3


def test_reserved_keyword_is_rejected_as_type_name() -> None:
    # "select" is a RESERVED_KEYWORD in every supported major; it cannot be
    # used unquoted as a type name.
    tokens = _tokens_for("select")
    result = parse_type_name(tokens, 0, _keywords_for(16))
    assert result is None


def test_quoted_reserved_word_is_accepted_as_type_name() -> None:
    tokens = _tokens_for('"select"')
    result = parse_type_name(tokens, 0, _keywords_for(16))
    assert result is not None
    type_name, idx = result
    assert idx == len(tokens)
    assert type_name.name.normalized == "select"


def test_unsupported_typmod_argument_kind_is_rejected() -> None:
    tokens = _tokens_for("varchar('20')")
    result = parse_type_name(tokens, 0, _keywords_for(16))
    assert result is None
