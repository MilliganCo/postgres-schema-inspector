"""Major-aware `ALTER TABLE` statement classifier (design section 1b).

Owns the `ALTER TABLE [IF EXISTS] [ONLY] <table> [*] <single_action>` prefix
and top-level multi-action rejection; delegates the single supported action
to `grammar_alter.py`. Called from the DB phase once a major-specific
`keyword_categories` map (`pg_get_keywords()`) is available; performs no
PostgreSQL/catalog access itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pginspect.impact.parser import grammar_alter
from pginspect.impact.parser.ast import (
    AlterClassification,
    QualifiedName,
    TableRef,
    Token,
    TokenKind,
    UnsupportedParserAst,
)


def _unsupported(reason: str) -> UnsupportedParserAst:
    return UnsupportedParserAst(reason=reason)


def _match_word(tokens: Sequence[Token], idx: int, word: str) -> bool:
    return (
        idx < len(tokens) and tokens[idx].kind is TokenKind.WORD and tokens[idx].normalized == word
    )


def _match_words(tokens: Sequence[Token], idx: int, words: tuple[str, ...]) -> bool:
    return all(_match_word(tokens, idx + offset, word) for offset, word in enumerate(words))


def classify_noncontrol_statement(
    tokens: Sequence[Token], keyword_categories: Mapping[str, str]
) -> AlterClassification:
    """Classify a non-control, non-empty statement's token stream.

    Returns a supported family AST node (`.family` in `{"type", "add",
    "drop"}`) or `UnsupportedParserAst` (`.family == .analysis_status ==
    "unsupported_parser"`). Dollar-quoted statement bodies are unsupported
    regardless of surrounding grammar, since they are lexically valid but not
    modeled by this grammar.
    """
    if any(tok.kind is TokenKind.DOLLAR_LITERAL for tok in tokens):
        return _unsupported("dollar-quoted body is not supported")

    if not _match_word(tokens, 0, "alter") or not _match_word(tokens, 1, "table"):
        return _unsupported("not an ALTER TABLE statement")

    idx = 2
    if_exists = False
    if _match_words(tokens, idx, ("if", "exists")):
        if_exists = True
        idx += 2

    if _match_word(tokens, idx, "only"):
        return _unsupported("ALTER TABLE ONLY is not supported")

    parsed_table = grammar_alter.parse_qualified_name(tokens, idx, keyword_categories)
    if parsed_table is None:
        return _unsupported("could not parse ALTER TABLE target table name")
    table_qname: QualifiedName
    table_qname, idx = parsed_table

    if idx < len(tokens) and tokens[idx].kind is TokenKind.PUNCTUATION and tokens[idx].raw == "*":
        return _unsupported("trailing '*' after table name is not supported")

    if grammar_alter.has_top_level_comma(tokens, idx):
        return _unsupported("multiple top-level ALTER TABLE actions are not supported")

    table_ref = TableRef(if_exists=if_exists, qualified_name=table_qname)

    if idx >= len(tokens):
        return _unsupported("ALTER TABLE statement is missing an action")

    action = tokens[idx]
    if action.kind is TokenKind.WORD and action.normalized == "alter":
        return grammar_alter.parse_type_action(tokens, idx, table_ref, keyword_categories)
    if action.kind is TokenKind.WORD and action.normalized == "add":
        return grammar_alter.parse_add_action(tokens, idx, table_ref, keyword_categories)
    if action.kind is TokenKind.WORD and action.normalized == "drop":
        return grammar_alter.parse_drop_action(tokens, idx, table_ref, keyword_categories)
    return _unsupported("unrecognized ALTER TABLE action")


__all__ = ["classify_noncontrol_statement"]
