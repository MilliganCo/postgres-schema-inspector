"""Lexical FSM: whole-file scanning and top-level statement splitting.

Design section 1.2. States: normal, single-quoted string, `E'...'` escape
string, double-quoted identifier, dollar-quoted string, line comment, nested
block comment. Terminator is top-level `;` or EOF; a `;` inside a string,
quoted identifier, or dollar-quoted body never terminates a statement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pginspect.impact.input import LocalPhaseError
from pginspect.impact.parser.ast import MAX_NESTED_BLOCK_COMMENT_DEPTH, MAX_STATEMENTS, SourceSpan


class LexemeKind(StrEnum):
    WHITESPACE = "whitespace"
    LINE_COMMENT = "line_comment"
    BLOCK_COMMENT = "block_comment"
    WORD = "word"
    QUOTED_IDENTIFIER = "quoted_identifier"
    STRING_LITERAL = "string_literal"
    BIT_LITERAL = "bit_literal"
    HEX_LITERAL = "hex_literal"
    NUMERIC_LITERAL = "numeric_literal"
    DOLLAR_LITERAL = "dollar_literal"
    PUNCTUATION = "punctuation"


_TRIVIA_KINDS = frozenset(
    {LexemeKind.WHITESPACE, LexemeKind.LINE_COMMENT, LexemeKind.BLOCK_COMMENT}
)


@dataclass(frozen=True)
class Lexeme:
    kind: LexemeKind
    raw: str
    span: SourceSpan


@dataclass(frozen=True)
class RawStatement:
    lexemes: tuple[Lexeme, ...]
    span: SourceSpan


def _read_quoted(text: str, i: int, *, quote: str, escape: bool) -> int:
    """`i` points at the opening quote. Returns the index just after the closer."""
    n = len(text)
    j = i + 1
    while j < n:
        c = text[j]
        if escape and c == "\\":
            j += 2
            continue
        if c == quote:
            if j + 1 < n and text[j + 1] == quote:
                j += 2
                continue
            return j + 1
        j += 1
    kind = "string" if quote == "'" else "quoted identifier"
    raise LocalPhaseError(f"Unterminated {kind} in migration file.")


def _match_dollar_open(text: str, i: int) -> tuple[str, int] | None:
    """`i` points at `$`. Returns `(delimiter, end_of_opening_index)` or `None`.

    A digit immediately after `$` (e.g. `$1`) is never a dollar-quote tag.
    """
    n = len(text)
    j = i + 1
    if j < n and (text[j].isalpha() or text[j] == "_"):
        j += 1
        while j < n and (text[j].isalnum() or text[j] == "_"):
            j += 1
    if j < n and text[j] == "$":
        return text[i : j + 1], j + 1
    return None


def _read_number(text: str, i: int) -> int:
    n = len(text)
    j = i
    if text[j] == ".":
        j += 1
        while j < n and text[j].isdigit():
            j += 1
    else:
        while j < n and text[j].isdigit():
            j += 1
        if j < n and text[j] == "." and not (j + 1 < n and text[j + 1] == "."):
            j += 1
            while j < n and text[j].isdigit():
                j += 1
    if j < n and text[j] in "eE":
        k = j + 1
        if k < n and text[k] in "+-":
            k += 1
        if k < n and text[k].isdigit():
            k += 1
            while k < n and text[k].isdigit():
                k += 1
            j = k
    return j


def _scan(text: str) -> list[Lexeme]:  # noqa: PLR0912, PLR0915 - single-pass lexical FSM
    lexemes: list[Lexeme] = []
    n = len(text)
    i = 0
    line = 1

    while i < n:
        ch = text[i]
        start_line = line

        if ch.isspace():
            j = i
            while j < n and text[j].isspace():
                if text[j] == "\n":
                    line += 1
                j += 1
            lexemes.append(
                Lexeme(LexemeKind.WHITESPACE, text[i:j], SourceSpan(start_line, line, i, j))
            )
            i = j
            continue

        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            j = i + 2
            while j < n and text[j] != "\n":
                j += 1
            lexemes.append(
                Lexeme(LexemeKind.LINE_COMMENT, text[i:j], SourceSpan(start_line, line, i, j))
            )
            i = j
            continue

        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            depth = 1
            j = i + 2
            while j < n and depth > 0:
                if text[j] == "\n":
                    line += 1
                    j += 1
                    continue
                if text[j] == "/" and j + 1 < n and text[j + 1] == "*":
                    depth += 1
                    if depth > MAX_NESTED_BLOCK_COMMENT_DEPTH:
                        raise LocalPhaseError("Block comment nesting exceeds the supported limit.")
                    j += 2
                    continue
                if text[j] == "*" and j + 1 < n and text[j + 1] == "/":
                    depth -= 1
                    j += 2
                    continue
                j += 1
            if depth > 0:
                raise LocalPhaseError("Unterminated block comment in migration file.")
            lexemes.append(
                Lexeme(LexemeKind.BLOCK_COMMENT, text[i:j], SourceSpan(start_line, line, i, j))
            )
            i = j
            continue

        if ch == "$":
            matched = _match_dollar_open(text, i)
            if matched is not None:
                tag_delim, open_end = matched
                close_idx = text.find(tag_delim, open_end)
                if close_idx == -1:
                    raise LocalPhaseError("Unterminated dollar-quoted string in migration file.")
                end = close_idx + len(tag_delim)
                line += text.count("\n", i, end)
                lexemes.append(
                    Lexeme(
                        LexemeKind.DOLLAR_LITERAL, text[i:end], SourceSpan(start_line, line, i, end)
                    )
                )
                i = end
                continue
            lexemes.append(
                Lexeme(LexemeKind.PUNCTUATION, "$", SourceSpan(start_line, start_line, i, i + 1))
            )
            i += 1
            continue

        if ch in "EeBbXx" and i + 1 < n and text[i + 1] == "'":
            prev = text[i - 1] if i > 0 else ""
            if not (prev.isalnum() or prev == "_"):
                end = _read_quoted(text, i + 1, quote="'", escape=ch in "Ee")
                line += text.count("\n", i, end)
                if ch in "Ee":
                    kind = LexemeKind.STRING_LITERAL
                elif ch in "Bb":
                    kind = LexemeKind.BIT_LITERAL
                else:
                    kind = LexemeKind.HEX_LITERAL
                lexemes.append(Lexeme(kind, text[i:end], SourceSpan(start_line, line, i, end)))
                i = end
                continue

        if ch == "'":
            end = _read_quoted(text, i, quote="'", escape=False)
            line += text.count("\n", i, end)
            lexemes.append(
                Lexeme(LexemeKind.STRING_LITERAL, text[i:end], SourceSpan(start_line, line, i, end))
            )
            i = end
            continue

        if ch == '"':
            end = _read_quoted(text, i, quote='"', escape=False)
            line += text.count("\n", i, end)
            lexemes.append(
                Lexeme(
                    LexemeKind.QUOTED_IDENTIFIER, text[i:end], SourceSpan(start_line, line, i, end)
                )
            )
            i = end
            continue

        if ch == "\\":
            raise LocalPhaseError(
                "psql backslash meta-commands are not supported in migration scripts."
            )

        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            j = _read_number(text, i)
            lexemes.append(
                Lexeme(
                    LexemeKind.NUMERIC_LITERAL, text[i:j], SourceSpan(start_line, start_line, i, j)
                )
            )
            i = j
            continue

        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            lexemes.append(
                Lexeme(LexemeKind.WORD, text[i:j], SourceSpan(start_line, start_line, i, j))
            )
            i = j
            continue

        lexemes.append(
            Lexeme(LexemeKind.PUNCTUATION, ch, SourceSpan(start_line, start_line, i, i + 1))
        )
        i += 1

    return lexemes


def split_statements(
    text: str, *, max_statements: int = MAX_STATEMENTS
) -> tuple[RawStatement, ...]:
    """Split `text` on top-level `;` into non-empty `RawStatement`s.

    Empty separators (`;;`, whitespace/comment-only segments) are dropped and
    never receive a `statement_index`. Raises `LocalPhaseError` on malformed
    lexical state (unclosed string/identifier/comment/dollar-quote), on a
    stray backslash outside strings/comments, on block-comment nesting past
    `MAX_NESTED_BLOCK_COMMENT_DEPTH`, or once the statement count would exceed
    `max_statements`.
    """
    lexemes = _scan(text)
    statements: list[RawStatement] = []
    current: list[Lexeme] = []

    def flush() -> None:
        nonlocal current
        meaningful = [lex for lex in current if lex.kind not in _TRIVIA_KINDS]
        if meaningful:
            if len(statements) >= max_statements:
                raise LocalPhaseError(
                    "Migration file exceeds the maximum supported statement count."
                )
            statements.append(
                RawStatement(
                    lexemes=tuple(current),
                    span=SourceSpan(
                        start_line=meaningful[0].span.start_line,
                        end_line=meaningful[-1].span.end_line,
                        start_offset=meaningful[0].span.start_offset,
                        end_offset=meaningful[-1].span.end_offset,
                    ),
                )
            )
        current = []

    for lex in lexemes:
        if lex.kind is LexemeKind.PUNCTUATION and lex.raw == ";":
            flush()
            continue
        current.append(lex)

    flush()

    return tuple(statements)
