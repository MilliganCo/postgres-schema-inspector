"""Minimal local-parser types and limits shared across the parser package.

Design section 1.2/1.3/1.7/1b. These types carry no PostgreSQL dependency;
`keyword_categories` (major-aware `pg_get_keywords()` catcodes) is supplied by
the DB phase and threaded through as a plain mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pginspect.impact.models.enums import AnalysisStatus

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


# --- Grammar boundary (design section 1b): TypeName AST-lite + family nodes.


@dataclass(frozen=True)
class Identifier:
    """A single (possibly quoted) identifier token, normalized per design §1b.

    `raw_token_private` is retained for span/debug purposes only; callers
    should use `value`/`normalized_value`, not the raw token, as the public
    identity of the identifier.
    """

    raw_token_private: Token
    value: str
    quoted: bool
    normalized_value: str
    source_span: SourceSpan


@dataclass(frozen=True)
class QualifiedName:
    """`schema.name`, an unqualified `name`, or a recognized multiword builtin.

    For multiword builtins (e.g. `double precision`), `schema` and `name` are
    both `None`; `normalized` carries the canonical space-joined phrase.
    """

    schema: Identifier | None
    name: Identifier | None
    normalized: str
    is_multiword_builtin: bool = False


@dataclass(frozen=True)
class TypmodArg:
    """One `TypeName` typmod argument: an integer literal or a limited identifier."""

    raw: str
    integer_value: int | None


@dataclass(frozen=True)
class ArrayBound:
    """One `[]` (unbound) or `[n]` (bound) array-bound suffix."""

    unbound: bool
    length: int | None


@dataclass(frozen=True)
class TypeName:
    name: QualifiedName
    typmod: tuple[TypmodArg, ...]
    array_bounds: tuple[ArrayBound, ...]
    source_span: SourceSpan


@dataclass(frozen=True)
class TableRef:
    if_exists: bool
    qualified_name: QualifiedName


@dataclass(frozen=True)
class SupportedAlterType:
    """`ALTER [COLUMN] col TYPE|SET DATA TYPE TypeName [COLLATE ...] [USING ...]`."""

    table: TableRef
    column: Identifier
    type_name: TypeName
    collation: QualifiedName | None
    using_expression_tokens: tuple[Token, ...]
    using_expression_span: SourceSpan | None
    family: Literal["type"] = "type"


@dataclass(frozen=True)
class SupportedAlterAdd:
    """`ADD [COLUMN] [IF NOT EXISTS] col TypeName [COLLATE] [DEFAULT] [NULL|NOT NULL]`."""

    table: TableRef
    column: Identifier
    if_not_exists: bool
    type_name: TypeName
    collation: QualifiedName | None
    default_expression_tokens: tuple[Token, ...]
    default_expression_span: SourceSpan | None
    nullability: Literal["unspecified", "null", "not_null"]
    family: Literal["add"] = "add"


@dataclass(frozen=True)
class SupportedAlterDrop:
    """`DROP [COLUMN] [IF EXISTS] col [RESTRICT | CASCADE]`."""

    table: TableRef
    column: Identifier
    if_exists: bool
    drop_behavior_written: Literal["default", "restrict", "cascade"]
    effective_behavior: Literal["restrict", "cascade"]
    family: Literal["drop"] = "drop"


@dataclass(frozen=True)
class UnsupportedParserAst:
    """Any statement the grammar declines to model (design §1.4/§1b)."""

    reason: str
    family: Literal["unsupported_parser"] = "unsupported_parser"
    analysis_status: AnalysisStatus = field(default=AnalysisStatus.UNSUPPORTED_PARSER)


AlterClassification = (
    SupportedAlterType | SupportedAlterAdd | SupportedAlterDrop | UnsupportedParserAst
)
