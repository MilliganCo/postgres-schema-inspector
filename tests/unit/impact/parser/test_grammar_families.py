"""Tests for `classify_noncontrol_statement` family grammars (design section 1b).

Keyword fixtures under `tests/fixtures/impact/keywords/pgNN.json` are parsed
from the real PostgreSQL `kwlist.h` sources for majors 14-18 (see
`docs/superpowers/plans/2026-07-29-change-impact.md`, Task 3, for the capture
deviation note: `PGINSPECT_TEST_DSN` was unreachable in this environment, so
`scripts/capture_pg_keywords.py` could not be run live).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pginspect.impact.models.enums import AnalysisStatus
from pginspect.impact.parser.ast import (
    SupportedAlterAdd,
    SupportedAlterDrop,
    SupportedAlterType,
    Token,
    UnsupportedParserAst,
)
from pginspect.impact.parser.classify import classify_noncontrol_statement
from pginspect.impact.parser.split import split_statements
from pginspect.impact.parser.tokens import tokenize

_KEYWORDS_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "impact" / "keywords"
_MAJORS = [14, 15, 16, 17, 18]


def _keywords_for(major: int) -> dict[str, str]:
    return json.loads((_KEYWORDS_ROOT / f"pg{major}.json").read_text(encoding="utf-8"))


def _tokens_for(sql: str) -> tuple[Token, ...]:
    (raw,) = split_statements(sql)
    return tokenize(raw)


def test_all_five_keyword_fixtures_exist_and_differ_across_majors() -> None:
    mappings = {major: _keywords_for(major) for major in _MAJORS}
    for major, mapping in mappings.items():
        assert len(mapping) > 400, major
    # Guard against a lazy "copy pg16 five times" deviation: at least one
    # word must have been added between the oldest and newest fixture.
    assert set(mappings[18]) - set(mappings[14])


@pytest.mark.parametrize("major", _MAJORS)
def test_alter_type_parses_on_major(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE s.t ALTER COLUMN c TYPE integer")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterType)
    assert result.family == "type"
    assert result.type_name.name.normalized == "integer"
    assert result.table.qualified_name.normalized == "s.t"
    assert result.column.normalized_value == "c"
    assert not result.table.if_exists


@pytest.mark.parametrize("major", _MAJORS)
def test_alter_set_data_type_with_using(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t ALTER COLUMN c SET DATA TYPE integer USING c::integer")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterType)
    assert result.type_name.name.normalized == "integer"
    assert result.using_expression_tokens
    assert result.using_expression_span is not None


@pytest.mark.parametrize("major", _MAJORS)
def test_alter_type_with_collate(major: int) -> None:
    tokens = _tokens_for('ALTER TABLE t ALTER COLUMN c TYPE text COLLATE "C"')
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterType)
    assert result.collation is not None
    assert result.collation.normalized == "C"


@pytest.mark.parametrize("major", _MAJORS)
def test_alter_type_without_column_keyword(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t ALTER c TYPE text")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterType)


@pytest.mark.parametrize("major", _MAJORS)
def test_alter_table_if_exists(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE IF EXISTS t ALTER COLUMN c TYPE text")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterType)
    assert result.table.if_exists


@pytest.mark.parametrize("major", _MAJORS)
def test_add_column_minimal(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t ADD COLUMN note text")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterAdd)
    assert result.family == "add"
    assert result.type_name.name.normalized == "text"
    assert not result.if_not_exists
    assert result.nullability == "unspecified"
    assert result.default_expression_tokens == ()


@pytest.mark.parametrize("major", _MAJORS)
def test_add_column_if_not_exists(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t ADD COLUMN IF NOT EXISTS note text")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterAdd)
    assert result.if_not_exists


@pytest.mark.parametrize("major", _MAJORS)
def test_add_column_without_column_keyword(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t ADD note text")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterAdd)


@pytest.mark.parametrize("major", _MAJORS)
def test_add_column_with_default_and_not_null(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t ADD COLUMN flag boolean DEFAULT false NOT NULL")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterAdd)
    assert result.nullability == "not_null"
    assert [tok.raw for tok in result.default_expression_tokens] == ["false"]


@pytest.mark.parametrize("major", _MAJORS)
def test_add_column_default_null_literal(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t ADD COLUMN note text DEFAULT NULL")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterAdd)
    assert result.nullability == "unspecified"
    assert [tok.normalized for tok in result.default_expression_tokens] == ["null"]


@pytest.mark.parametrize("major", _MAJORS)
def test_add_column_null_before_default(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t ADD COLUMN note text NULL DEFAULT 'x'")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterAdd)
    assert result.nullability == "null"
    assert result.default_expression_tokens


@pytest.mark.parametrize("major", _MAJORS)
def test_add_column_qualified_function_default(major: int) -> None:
    tokens = _tokens_for(
        "ALTER TABLE t ADD COLUMN seen_at timestamptz DEFAULT pg_catalog.clock_timestamp()"
    )
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterAdd)
    assert [tok.raw for tok in result.default_expression_tokens] == [
        "pg_catalog",
        ".",
        "clock_timestamp",
        "(",
        ")",
    ]


@pytest.mark.parametrize(
    "clause",
    [
        "CONSTRAINT ck CHECK (note IS NOT NULL)",
        "UNIQUE",
        "PRIMARY KEY",
        "REFERENCES other(id)",
        "GENERATED ALWAYS AS IDENTITY",
    ],
)
@pytest.mark.parametrize("major", _MAJORS)
def test_add_column_unsupported_clauses(clause: str, major: int) -> None:
    tokens = _tokens_for(f"ALTER TABLE t ADD COLUMN note text {clause}")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, UnsupportedParserAst)
    assert result.analysis_status == AnalysisStatus.UNSUPPORTED_PARSER


@pytest.mark.parametrize("major", _MAJORS)
def test_drop_column_minimal(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t DROP COLUMN obsolete")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterDrop)
    assert result.family == "drop"
    assert result.drop_behavior_written == "default"
    assert result.effective_behavior == "restrict"
    assert not result.if_exists


@pytest.mark.parametrize("major", _MAJORS)
def test_drop_column_if_exists(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t DROP COLUMN IF EXISTS obsolete")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterDrop)
    assert result.if_exists


@pytest.mark.parametrize("major", _MAJORS)
def test_drop_column_without_column_keyword(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t DROP obsolete")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterDrop)


@pytest.mark.parametrize("major", _MAJORS)
def test_drop_column_restrict(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t DROP COLUMN secret RESTRICT")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterDrop)
    assert result.drop_behavior_written == "restrict"
    assert result.effective_behavior == "restrict"


@pytest.mark.parametrize("major", _MAJORS)
def test_drop_column_cascade(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t DROP COLUMN secret CASCADE")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, SupportedAlterDrop)
    assert result.drop_behavior_written == "cascade"
    assert result.effective_behavior == "cascade"


@pytest.mark.parametrize("major", _MAJORS)
def test_multi_action_comma_is_unsupported(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t ADD COLUMN a int, ADD COLUMN b int")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, UnsupportedParserAst)
    assert result.family == "unsupported_parser"
    assert result.analysis_status == AnalysisStatus.UNSUPPORTED_PARSER


@pytest.mark.parametrize("major", _MAJORS)
def test_dollar_quoted_body_is_unsupported(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t ADD COLUMN note text DEFAULT $$literal$$")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, UnsupportedParserAst)


@pytest.mark.parametrize("major", _MAJORS)
def test_only_is_unsupported(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE ONLY t ADD COLUMN note text")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, UnsupportedParserAst)


@pytest.mark.parametrize("major", _MAJORS)
def test_trailing_star_is_unsupported(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t * ADD COLUMN note text")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, UnsupportedParserAst)


@pytest.mark.parametrize("major", _MAJORS)
def test_only_and_if_exists_together_is_unsupported(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE IF EXISTS ONLY t ADD COLUMN note text")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, UnsupportedParserAst)


@pytest.mark.parametrize("major", _MAJORS)
def test_non_alter_table_statement_is_unsupported(major: int) -> None:
    tokens = _tokens_for("CREATE TABLE other (id int)")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, UnsupportedParserAst)


@pytest.mark.parametrize("major", _MAJORS)
def test_unrecognized_alter_table_action_is_unsupported(major: int) -> None:
    tokens = _tokens_for("ALTER TABLE t RENAME COLUMN a TO b")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, UnsupportedParserAst)


@pytest.mark.parametrize("major", _MAJORS)
def test_drop_index_family_is_not_recognized(major: int) -> None:
    tokens = _tokens_for("DROP INDEX idx")
    result = classify_noncontrol_statement(tokens, _keywords_for(major))
    assert isinstance(result, UnsupportedParserAst)
