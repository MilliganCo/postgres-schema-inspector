"""Minimal local-parser types and limits shared across the parser package.

Design section 1.2/1.3/1.7. These types carry no PostgreSQL dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MAX_FILE_SIZE_BYTES = 4 * 1024 * 1024
MAX_STATEMENTS = 1000
MAX_TOKENS_PER_STATEMENT = 10000
MAX_NESTED_BLOCK_COMMENT_DEPTH = 64
MAX_PREVIEW_CODEPOINTS = 240


@dataclass(frozen=True)
class SourceSpan:
    start_line: int
    end_line: int
    start_offset: int
    end_offset: int


class TokenKind(StrEnum):
    WORD = "word"
    QUOTED_IDENTIFIER = "quoted_identifier"
    STRING_LITERAL = "string_literal"
    NUMERIC_LITERAL = "numeric_literal"
    BIT_LITERAL = "bit_literal"
    HEX_LITERAL = "hex_literal"
    DOLLAR_LITERAL = "dollar_literal"
    PUNCTUATION = "punctuation"


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    raw: str
    normalized: str
    span: SourceSpan
