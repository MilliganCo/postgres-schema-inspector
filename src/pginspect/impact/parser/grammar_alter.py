"""Major-aware `ALTER TABLE` family grammar (design section 1b).

This module owns `TypeName` parsing and the three supported single-action
family grammars (`TYPE` / `ADD` / `DROP`). `classify.py` owns the `ALTER
TABLE [IF EXISTS] [ONLY] <table> [*] <single_action>` prefix and dispatches
to the family parsers below. No PostgreSQL/catalog access anywhere here;
`keyword_categories` is a plain `word -> catcode` mapping captured elsewhere
via `pg_get_keywords()`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pginspect.impact.parser.ast import (
    ArrayBound,
    Identifier,
    QualifiedName,
    SourceSpan,
    SupportedAlterAdd,
    SupportedAlterDrop,
    SupportedAlterType,
    TableRef,
    Token,
    TokenKind,
    TypeName,
    TypmodArg,
    UnsupportedParserAst,
)

_RESERVED_CATCODE = "R"

_ADD_UNSUPPORTED_CLAUSE_KEYWORDS = frozenset(
    {"constraint", "check", "references", "unique", "primary", "generated", "identity"}
)

# (exact case-insensitive word sequence, canonical normalized phrase); matched
# longest-sequence-first so e.g. "national character varying" wins over
# "national character" over a bare "national" (which is not itself a builtin).
_MULTIWORD_BUILTINS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("double", "precision"), "double precision"),
    (("national", "character", "varying"), "national character varying"),
    (("national", "character"), "national character"),
    (("national", "char"), "national char"),
    (("character", "varying"), "character varying"),
    (("bit", "varying"), "bit varying"),
    (("character",), "character"),
    (("char",), "char"),
    (("varchar",), "varchar"),
    (("time", "with", "time", "zone"), "time with time zone"),
    (("time", "without", "time", "zone"), "time without time zone"),
    (("timestamp", "with", "time", "zone"), "timestamp with time zone"),
    (("timestamp", "without", "time", "zone"), "timestamp without time zone"),
    (("interval",), "interval"),
)
_MULTIWORD_BUILTINS_SORTED = tuple(sorted(_MULTIWORD_BUILTINS, key=lambda pair: -len(pair[0])))


def _unsupported(reason: str) -> UnsupportedParserAst:
    return UnsupportedParserAst(reason=reason)


def _match_word(tokens: Sequence[Token], idx: int, word: str) -> bool:
    return (
        idx < len(tokens) and tokens[idx].kind is TokenKind.WORD and tokens[idx].normalized == word
    )


def _match_words(tokens: Sequence[Token], idx: int, words: tuple[str, ...]) -> bool:
    return all(_match_word(tokens, idx + offset, word) for offset, word in enumerate(words))


def _match_punctuation(tokens: Sequence[Token], idx: int, raw: str) -> bool:
    return (
        idx < len(tokens) and tokens[idx].kind is TokenKind.PUNCTUATION and tokens[idx].raw == raw
    )


def _is_identifier_token(tok: Token) -> bool:
    return tok.kind in (TokenKind.WORD, TokenKind.QUOTED_IDENTIFIER)


def _identifier_allowed(tok: Token, keyword_categories: Mapping[str, str]) -> bool:
    if tok.kind is TokenKind.QUOTED_IDENTIFIER:
        return True
    return keyword_categories.get(tok.normalized) != _RESERVED_CATCODE


def _identifier_from_token(tok: Token) -> Identifier:
    return Identifier(
        raw_token_private=tok,
        value=tok.raw,
        quoted=tok.kind is TokenKind.QUOTED_IDENTIFIER,
        normalized_value=tok.normalized,
        source_span=tok.span,
    )


def _span_of(tokens: Sequence[Token]) -> SourceSpan:
    first, last = tokens[0].span, tokens[-1].span
    return SourceSpan(
        start_line=first.start_line,
        end_line=last.end_line,
        start_offset=first.start_offset,
        end_offset=last.end_offset,
    )


def _numeric_literal_int(tok: Token) -> int | None:
    try:
        return int(tok.raw)
    except ValueError:
        return None


def parse_identifier(
    tokens: Sequence[Token], idx: int, keyword_categories: Mapping[str, str]
) -> tuple[Identifier, int] | None:
    """A single (non schema-qualified) identifier, e.g. a column name."""
    if idx >= len(tokens):
        return None
    tok = tokens[idx]
    if not _is_identifier_token(tok) or not _identifier_allowed(tok, keyword_categories):
        return None
    return _identifier_from_token(tok), idx + 1


def parse_qualified_name(
    tokens: Sequence[Token], idx: int, keyword_categories: Mapping[str, str]
) -> tuple[QualifiedName, int] | None:
    """`schema.name` or unqualified `name`, e.g. a table or collation name."""
    if idx >= len(tokens):
        return None
    tok = tokens[idx]
    if not _is_identifier_token(tok) or not _identifier_allowed(tok, keyword_categories):
        return None
    first = _identifier_from_token(tok)
    next_idx = idx + 1
    if _match_punctuation(tokens, next_idx, "."):
        if next_idx + 1 >= len(tokens):
            return None
        tok2 = tokens[next_idx + 1]
        if not _is_identifier_token(tok2) or not _identifier_allowed(tok2, keyword_categories):
            return None
        second = _identifier_from_token(tok2)
        qname = QualifiedName(
            schema=first,
            name=second,
            normalized=f"{first.normalized_value}.{second.normalized_value}",
        )
        return qname, next_idx + 2
    return QualifiedName(schema=None, name=first, normalized=first.normalized_value), next_idx


def _match_multiword_builtin(tokens: Sequence[Token], idx: int) -> tuple[str, int] | None:
    for words, canonical in _MULTIWORD_BUILTINS_SORTED:
        n = len(words)
        if idx + n > len(tokens):
            continue
        candidate = tokens[idx : idx + n]
        if (
            all(tok.kind is TokenKind.WORD for tok in candidate)
            and tuple(tok.normalized for tok in candidate) == words
        ):
            return canonical, n
    return None


def _parse_typmod(tokens: Sequence[Token], idx: int) -> tuple[tuple[TypmodArg, ...], int] | None:
    """`idx` points at the opening `(`. A required non-empty comma-separated list."""
    idx += 1
    if _match_punctuation(tokens, idx, ")"):
        return None
    args: list[TypmodArg] = []
    while True:
        if idx >= len(tokens):
            return None
        tok = tokens[idx]
        if tok.kind is TokenKind.NUMERIC_LITERAL:
            args.append(TypmodArg(raw=tok.raw, integer_value=_numeric_literal_int(tok)))
            idx += 1
        elif tok.kind is TokenKind.WORD:
            args.append(TypmodArg(raw=tok.raw, integer_value=None))
            idx += 1
        else:
            return None
        if _match_punctuation(tokens, idx, ","):
            idx += 1
            continue
        if _match_punctuation(tokens, idx, ")"):
            idx += 1
            break
        return None
    return tuple(args), idx


def parse_type_name(
    tokens: Sequence[Token], idx: int, keyword_categories: Mapping[str, str]
) -> tuple[TypeName, int] | None:
    """`TypeName` per design §1b: multiword builtin or qualified name, plus
    optional typmod parens and array-bound suffixes."""
    start = idx
    matched = _match_multiword_builtin(tokens, idx)
    if matched is not None:
        canonical, consumed = matched
        name = QualifiedName(
            schema=None, name=None, normalized=canonical, is_multiword_builtin=True
        )
        idx += consumed
    else:
        parsed_name = parse_qualified_name(tokens, idx, keyword_categories)
        if parsed_name is None:
            return None
        name, idx = parsed_name

    typmod: tuple[TypmodArg, ...] = ()
    if _match_punctuation(tokens, idx, "("):
        parsed_typmod = _parse_typmod(tokens, idx)
        if parsed_typmod is None:
            return None
        typmod, idx = parsed_typmod

    bounds: list[ArrayBound] = []
    while _match_punctuation(tokens, idx, "["):
        idx += 1
        if _match_punctuation(tokens, idx, "]"):
            bounds.append(ArrayBound(unbound=True, length=None))
            idx += 1
            continue
        if idx < len(tokens) and tokens[idx].kind is TokenKind.NUMERIC_LITERAL:
            length = _numeric_literal_int(tokens[idx])
            if length is None:
                return None
            idx += 1
            if not _match_punctuation(tokens, idx, "]"):
                return None
            bounds.append(ArrayBound(unbound=False, length=length))
            idx += 1
            continue
        return None

    return TypeName(
        name=name,
        typmod=typmod,
        array_bounds=tuple(bounds),
        source_span=_span_of(tokens[start:idx]),
    ), idx


def has_top_level_comma(tokens: Sequence[Token], idx: int) -> bool:
    depth = 0
    for tok in tokens[idx:]:
        if tok.kind is TokenKind.PUNCTUATION and tok.raw == "(":
            depth += 1
        elif tok.kind is TokenKind.PUNCTUATION and tok.raw == ")":
            depth -= 1
        elif depth == 0 and tok.kind is TokenKind.PUNCTUATION and tok.raw == ",":
            return True
    return False


def _balanced_parens(tokens: Sequence[Token]) -> bool:
    depth = 0
    for tok in tokens:
        if tok.kind is TokenKind.PUNCTUATION and tok.raw == "(":
            depth += 1
        elif tok.kind is TokenKind.PUNCTUATION and tok.raw == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def parse_type_action(
    tokens: Sequence[Token], idx: int, table_ref: TableRef, keyword_categories: Mapping[str, str]
) -> SupportedAlterType | UnsupportedParserAst:
    """`idx` points at the action-level `ALTER` keyword."""
    idx += 1
    if _match_word(tokens, idx, "column"):
        idx += 1
    parsed_column = parse_identifier(tokens, idx, keyword_categories)
    if parsed_column is None:
        return _unsupported("could not parse ALTER COLUMN target column name")
    column, idx = parsed_column

    if _match_word(tokens, idx, "type"):
        idx += 1
    elif _match_words(tokens, idx, ("set", "data", "type")):
        idx += 3
    else:
        return _unsupported("expected TYPE or SET DATA TYPE")

    parsed_type = parse_type_name(tokens, idx, keyword_categories)
    if parsed_type is None:
        return _unsupported("could not parse TypeName")
    type_name, idx = parsed_type

    collation: QualifiedName | None = None
    if _match_word(tokens, idx, "collate"):
        idx += 1
        parsed_collation = parse_qualified_name(tokens, idx, keyword_categories)
        if parsed_collation is None:
            return _unsupported("could not parse COLLATE qualifier")
        collation, idx = parsed_collation

    using_tokens: tuple[Token, ...] = ()
    using_span: SourceSpan | None = None
    if _match_word(tokens, idx, "using"):
        idx += 1
        expr_tokens = tuple(tokens[idx:])
        if not expr_tokens:
            return _unsupported("USING requires a non-empty expression")
        if not _balanced_parens(expr_tokens):
            return _unsupported("USING expression has unbalanced parentheses")
        using_tokens = expr_tokens
        using_span = _span_of(expr_tokens)
        idx = len(tokens)

    if idx != len(tokens):
        return _unsupported("unexpected trailing tokens after ALTER COLUMN TYPE clause")

    return SupportedAlterType(
        table=table_ref,
        column=column,
        type_name=type_name,
        collation=collation,
        using_expression_tokens=using_tokens,
        using_expression_span=using_span,
    )


def _scan_default_expression_end(tokens: Sequence[Token], start: int) -> int:
    """Opaque DEFAULT expression scan (design: "no default_is_literal_like in
    parser"). Stops at a top-level (paren-depth 0) `COLLATE`, a top-level
    `NOT NULL`, or a top-level bare `NULL` that is not the expression's very
    first token (so a literal `DEFAULT NULL` is still captured)."""
    depth = 0
    j = start
    is_first = True
    while j < len(tokens):
        tok = tokens[j]
        if tok.kind is TokenKind.PUNCTUATION and tok.raw == "(":
            depth += 1
        elif tok.kind is TokenKind.PUNCTUATION and tok.raw == ")":
            depth -= 1
        elif depth == 0 and tok.kind is TokenKind.WORD:
            word = tok.normalized
            if word == "collate":
                break
            if word == "not" and _match_word(tokens, j + 1, "null"):
                break
            if word == "null" and not is_first:
                break
        j += 1
        is_first = False
    return j


def parse_add_action(
    tokens: Sequence[Token], idx: int, table_ref: TableRef, keyword_categories: Mapping[str, str]
) -> SupportedAlterAdd | UnsupportedParserAst:
    """`idx` points at the action-level `ADD` keyword."""
    idx += 1
    if _match_word(tokens, idx, "column"):
        idx += 1
    if_not_exists = False
    if _match_words(tokens, idx, ("if", "not", "exists")):
        if_not_exists = True
        idx += 3

    parsed_column = parse_identifier(tokens, idx, keyword_categories)
    if parsed_column is None:
        return _unsupported("could not parse ADD COLUMN target column name")
    column, idx = parsed_column

    parsed_type = parse_type_name(tokens, idx, keyword_categories)
    if parsed_type is None:
        return _unsupported("could not parse TypeName")
    type_name, idx = parsed_type

    collation: QualifiedName | None = None
    default_tokens: tuple[Token, ...] = ()
    default_span: SourceSpan | None = None
    default_seen = False
    nullability: str = "unspecified"

    while idx < len(tokens):
        tok = tokens[idx]
        if tok.kind is not TokenKind.WORD:
            return _unsupported("unexpected trailing tokens after ADD COLUMN clause")
        word = tok.normalized

        if word == "collate":
            if collation is not None:
                return _unsupported("duplicate COLLATE clause")
            idx += 1
            parsed_collation = parse_qualified_name(tokens, idx, keyword_categories)
            if parsed_collation is None:
                return _unsupported("could not parse COLLATE qualifier")
            collation, idx = parsed_collation
            continue

        if word == "default":
            if default_seen:
                return _unsupported("duplicate DEFAULT clause")
            idx += 1
            end = _scan_default_expression_end(tokens, idx)
            if end == idx:
                return _unsupported("DEFAULT requires a non-empty expression")
            default_tokens = tuple(tokens[idx:end])
            default_span = _span_of(default_tokens)
            default_seen = True
            idx = end
            continue

        if word == "null":
            if nullability != "unspecified":
                return _unsupported("duplicate nullability clause")
            nullability = "null"
            idx += 1
            continue

        if word == "not" and _match_word(tokens, idx + 1, "null"):
            if nullability != "unspecified":
                return _unsupported("duplicate nullability clause")
            nullability = "not_null"
            idx += 2
            continue

        if word in _ADD_UNSUPPORTED_CLAUSE_KEYWORDS:
            return _unsupported(f"ADD COLUMN clause '{word}' is not supported")

        return _unsupported("unexpected trailing tokens after ADD COLUMN clause")

    return SupportedAlterAdd(
        table=table_ref,
        column=column,
        if_not_exists=if_not_exists,
        type_name=type_name,
        collation=collation,
        default_expression_tokens=default_tokens,
        default_expression_span=default_span,
        nullability=nullability,  # type: ignore[arg-type]
    )


def parse_drop_action(
    tokens: Sequence[Token], idx: int, table_ref: TableRef, keyword_categories: Mapping[str, str]
) -> SupportedAlterDrop | UnsupportedParserAst:
    """`idx` points at the action-level `DROP` keyword."""
    idx += 1
    if _match_word(tokens, idx, "column"):
        idx += 1
    if_exists = False
    if _match_words(tokens, idx, ("if", "exists")):
        if_exists = True
        idx += 2

    parsed_column = parse_identifier(tokens, idx, keyword_categories)
    if parsed_column is None:
        return _unsupported("could not parse DROP COLUMN target column name")
    column, idx = parsed_column

    drop_behavior_written: str = "default"
    if idx < len(tokens):
        if _match_word(tokens, idx, "restrict"):
            drop_behavior_written = "restrict"
            idx += 1
        elif _match_word(tokens, idx, "cascade"):
            drop_behavior_written = "cascade"
            idx += 1
        else:
            return _unsupported("unexpected trailing tokens after DROP COLUMN clause")

    if idx != len(tokens):
        return _unsupported("unexpected trailing tokens after DROP COLUMN clause")

    effective_behavior = "cascade" if drop_behavior_written == "cascade" else "restrict"
    return SupportedAlterDrop(
        table=table_ref,
        column=column,
        if_exists=if_exists,
        drop_behavior_written=drop_behavior_written,  # type: ignore[arg-type]
        effective_behavior=effective_behavior,  # type: ignore[arg-type]
    )


__all__ = [
    "has_top_level_comma",
    "parse_add_action",
    "parse_drop_action",
    "parse_identifier",
    "parse_qualified_name",
    "parse_type_action",
    "parse_type_name",
]
