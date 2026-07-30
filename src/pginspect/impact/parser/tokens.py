"""Tokenizer, sanitized preview, and statement fingerprint.

Design section 1.3 / 1.7. Comments and whitespace never become tokens;
literal values are redacted to typed placeholders before they can reach a
preview or a fingerprint input stream.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from pginspect.impact.input import LocalPhaseError
from pginspect.impact.parser.ast import (
    MAX_PREVIEW_CODEPOINTS,
    MAX_TOKENS_PER_STATEMENT,
    Token,
    TokenKind,
)
from pginspect.impact.parser.split import Lexeme, LexemeKind, RawStatement

_LITERAL_LEXEME_KINDS: dict[LexemeKind, TokenKind] = {
    LexemeKind.STRING_LITERAL: TokenKind.STRING_LITERAL,
    LexemeKind.BIT_LITERAL: TokenKind.BIT_LITERAL,
    LexemeKind.HEX_LITERAL: TokenKind.HEX_LITERAL,
    LexemeKind.DOLLAR_LITERAL: TokenKind.DOLLAR_LITERAL,
    LexemeKind.NUMERIC_LITERAL: TokenKind.NUMERIC_LITERAL,
}

_LITERAL_PLACEHOLDER: dict[TokenKind, str] = {
    TokenKind.STRING_LITERAL: "<string>",
    TokenKind.BIT_LITERAL: "<bit>",
    TokenKind.HEX_LITERAL: "<hex>",
    TokenKind.DOLLAR_LITERAL: "<dollar_body>",
    TokenKind.NUMERIC_LITERAL: "<number>",
}

_TRIVIA_LEXEME_KINDS = frozenset(
    {LexemeKind.WHITESPACE, LexemeKind.LINE_COMMENT, LexemeKind.BLOCK_COMMENT}
)


def _normalize_quoted_identifier(raw: str) -> str:
    return raw[1:-1].replace('""', '"')


def _lexeme_to_token(lex: Lexeme) -> Token:
    if lex.kind is LexemeKind.WORD:
        return Token(kind=TokenKind.WORD, raw=lex.raw, normalized=lex.raw.lower(), span=lex.span)
    if lex.kind is LexemeKind.QUOTED_IDENTIFIER:
        return Token(
            kind=TokenKind.QUOTED_IDENTIFIER,
            raw=lex.raw,
            normalized=_normalize_quoted_identifier(lex.raw),
            span=lex.span,
        )
    if lex.kind is LexemeKind.PUNCTUATION:
        return Token(kind=TokenKind.PUNCTUATION, raw=lex.raw, normalized=lex.raw, span=lex.span)
    token_kind = _LITERAL_LEXEME_KINDS[lex.kind]
    return Token(
        kind=token_kind, raw=lex.raw, normalized=_LITERAL_PLACEHOLDER[token_kind], span=lex.span
    )


def tokenize(
    raw_statement: RawStatement, *, max_tokens: int = MAX_TOKENS_PER_STATEMENT
) -> tuple[Token, ...]:
    """Convert a split statement's lexemes into a redaction-aware `Token` stream.

    Comments/whitespace are dropped. Raises `LocalPhaseError` once the token
    count for a single statement would exceed `max_tokens`.
    """
    out: list[Token] = []
    for lex in raw_statement.lexemes:
        if lex.kind in _TRIVIA_LEXEME_KINDS:
            continue
        if len(out) >= max_tokens:
            raise LocalPhaseError("Statement exceeds the maximum supported token count.")
        out.append(_lexeme_to_token(lex))
    return tuple(out)


def sanitized_preview(
    tokens: Sequence[Token], *, max_codepoints: int = MAX_PREVIEW_CODEPOINTS
) -> str:
    """Comment-free, whitespace-collapsed preview with literals replaced by
    typed placeholders; never falls back to raw SQL text. Truncated to
    `max_codepoints` Unicode code points.
    """
    parts = [
        _LITERAL_PLACEHOLDER[tok.kind] if tok.kind in _LITERAL_PLACEHOLDER else tok.raw
        for tok in tokens
    ]
    preview = " ".join(parts)
    return preview[:max_codepoints]


def statement_fingerprint(tokens: Sequence[Token]) -> str:
    """`sha256:` + first 16 hex of the SHA-256 digest of the canonical redacted
    token stream. Literal tokens contribute only their typed placeholder, so
    the migration's literal values never reach the fingerprint input.
    """
    canonical = "\x1f".join(f"{tok.kind.value}:{tok.normalized}" for tok in tokens)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"
