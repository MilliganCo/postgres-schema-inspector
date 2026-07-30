"""Exact, case-insensitive control-statement recognizer.

Design section 1.5. Local phase only: used for control-only file rejection
and ordinal assignment/card-skipping. Never used to classify arbitrary SQL
as supported/unsupported and never calls `pg_get_keywords()`.
"""

from __future__ import annotations

from collections.abc import Sequence

from pginspect.impact.parser.ast import Token, TokenKind

_CONTROL_FORMS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("BEGIN",),
        ("BEGIN", "WORK"),
        ("BEGIN", "TRANSACTION"),
        ("START", "TRANSACTION"),
        ("COMMIT",),
        ("COMMIT", "WORK"),
        ("COMMIT", "TRANSACTION"),
        ("END",),
        ("END", "WORK"),
        ("END", "TRANSACTION"),
    }
)


def is_control_statement(tokens: Sequence[Token]) -> bool:
    """`True` only for an exact match against `_CONTROL_FORMS` (no extra clauses).

    Comments are already excluded from `tokens` by the tokenizer, so a
    comment between control words does not defeat recognition.
    """
    if not tokens or any(tok.kind is not TokenKind.WORD for tok in tokens):
        return False
    words = tuple(tok.raw.upper() for tok in tokens)
    return words in _CONTROL_FORMS
