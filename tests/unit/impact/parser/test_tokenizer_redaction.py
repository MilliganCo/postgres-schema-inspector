"""Tests for the tokenizer, sanitized preview, and statement fingerprint.

Design section 1.3 / 1.7.
"""

from __future__ import annotations

import re

import pytest

from pginspect.impact.input import LocalPhaseError
from pginspect.impact.parser.ast import Token
from pginspect.impact.parser.split import split_statements
from pginspect.impact.parser.tokens import sanitized_preview, statement_fingerprint, tokenize

_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{16}$")


def _tokens_for(sql: str) -> tuple[Token, ...]:
    (raw,) = split_statements(sql)
    return tokenize(raw)


def test_tokenize_drops_comments_and_whitespace() -> None:
    tokens = _tokens_for("SELECT   1 -- trailing comment\n /* block */ FROM t;")
    assert [t.raw for t in tokens] == ["SELECT", "1", "FROM", "t"]


def test_tokenize_enforces_max_tokens_per_statement() -> None:
    sql = "SELECT " + " ".join(["a"] * 10001) + ";"
    (raw,) = split_statements(sql)
    with pytest.raises(LocalPhaseError):
        tokenize(raw, max_tokens=10000)


def test_tokenize_accepts_exactly_max_tokens() -> None:
    sql = "SELECT " + " ".join(["a"] * 9999) + ";"
    (raw,) = split_statements(sql)
    tokens = tokenize(raw, max_tokens=10000)
    assert len(tokens) == 10000


def test_sanitized_preview_replaces_string_literal_with_placeholder() -> None:
    tokens = _tokens_for("ALTER TABLE t ADD COLUMN x text DEFAULT 'secret';")
    preview = sanitized_preview(tokens)
    assert "secret" not in preview
    assert "<string>" in preview


def test_sanitized_preview_replaces_numeric_literal_with_placeholder() -> None:
    tokens = _tokens_for("SELECT 42;")
    preview = sanitized_preview(tokens)
    assert "42" not in preview
    assert "<number>" in preview


def test_sanitized_preview_replaces_dollar_literal_with_placeholder() -> None:
    tokens = _tokens_for("SELECT $$ secret body $$;")
    preview = sanitized_preview(tokens)
    assert "secret body" not in preview
    assert "<dollar_body>" in preview


def test_sanitized_preview_truncated_to_240_codepoints() -> None:
    long_name = "a" * 400
    tokens = _tokens_for(f"SELECT {long_name};")
    preview = sanitized_preview(tokens)
    assert len(preview) <= 240


def test_sanitized_preview_keeps_plain_identifiers() -> None:
    tokens = _tokens_for("ALTER TABLE t ADD COLUMN note text;")
    preview = sanitized_preview(tokens)
    assert preview == "ALTER TABLE t ADD COLUMN note text"


def test_statement_fingerprint_format() -> None:
    fp = statement_fingerprint(_tokens_for("SELECT 1;"))
    assert _FINGERPRINT_RE.match(fp)


def test_statement_fingerprint_is_stable_for_identical_statements() -> None:
    fp1 = statement_fingerprint(_tokens_for("SELECT 1;"))
    fp2 = statement_fingerprint(_tokens_for("SELECT 1;"))
    assert fp1 == fp2


def test_statement_fingerprint_identical_for_differing_literal_values() -> None:
    # Literals are redacted before hashing, so differing literal VALUES with
    # the same token shape legitimately fingerprint identically.
    fp_a = statement_fingerprint(_tokens_for("SELECT 'a';"))
    fp_b = statement_fingerprint(_tokens_for("SELECT 'b';"))
    assert fp_a == fp_b


def test_statement_fingerprint_differs_for_different_shapes() -> None:
    fp1 = statement_fingerprint(_tokens_for("SELECT 1;"))
    fp2 = statement_fingerprint(_tokens_for("SELECT 1, 2;"))
    assert fp1 != fp2


def test_canary_absent_from_preview_and_fingerprint_stream() -> None:
    canary = "CANARY_SECRET_7f03"
    tokens = _tokens_for(f"ALTER TABLE t ADD COLUMN x text DEFAULT '{canary}';")

    preview = sanitized_preview(tokens)
    assert canary not in preview

    canonical = "\x1f".join(f"{tok.kind.value}:{tok.normalized}" for tok in tokens)
    assert canary not in canonical

    fingerprint = statement_fingerprint(tokens)
    assert canary not in fingerprint
