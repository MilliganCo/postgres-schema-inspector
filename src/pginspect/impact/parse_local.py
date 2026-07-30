"""Local input -> `LocalParsedScript` assembly (design section 1; plan Task 2).

No PostgreSQL access anywhere in this module. `parse_migration_path` performs
the entire local phase: load -> split -> tokenize -> control-tag, raising
`LocalPhaseError` for every exit-4 (local/malformed) condition.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pginspect.impact.input import LocalPhaseError, load_migration_source
from pginspect.impact.parser.ast import MAX_STATEMENTS, MAX_TOKENS_PER_STATEMENT, Token, TokenKind
from pginspect.impact.parser.control import is_control_statement
from pginspect.impact.parser.split import split_statements
from pginspect.impact.parser.tokens import sanitized_preview, statement_fingerprint, tokenize

__all__ = [
    "LocalParsedScript",
    "LocalPhaseError",
    "LocalStatement",
    "parse_migration_path",
]


@dataclass(frozen=True)
class LocalStatement:
    statement_index: int
    is_control: bool
    start_line: int
    end_line: int
    tokens: tuple[Token, ...]
    statement_fingerprint: str
    sanitized_preview: str


@dataclass(frozen=True)
class LocalParsedScript:
    path_basename: str
    statements: tuple[LocalStatement, ...]
    control_ordinals: tuple[int, ...]
    source_statement_count: int


def _looks_like_copy_from_stdin(tokens: Sequence[Token]) -> bool:
    words = [tok.raw.upper() for tok in tokens if tok.kind is TokenKind.WORD]
    if not words or words[0] != "COPY":
        return False
    return any(words[i] == "FROM" and words[i + 1] == "STDIN" for i in range(len(words) - 1))


def parse_migration_path(path: Path) -> LocalParsedScript:
    """Load + split + tokenize + control-tag. Raises `LocalPhaseError` on all
    exit-4 conditions (malformed input, resource limits, unsupported psql/COPY
    constructs, empty/comment-only/control-only scripts).
    """
    loaded = load_migration_source(path)
    raw_statements = split_statements(loaded.text, max_statements=MAX_STATEMENTS)
    if not raw_statements:
        raise LocalPhaseError("No SQL statements found in migration file.")

    statements: list[LocalStatement] = []
    control_ordinals: list[int] = []
    has_analyzable_statement = False

    for index, raw in enumerate(raw_statements, start=1):
        stmt_tokens = tokenize(raw, max_tokens=MAX_TOKENS_PER_STATEMENT)
        if _looks_like_copy_from_stdin(stmt_tokens):
            raise LocalPhaseError("COPY ... FROM STDIN is not supported in migration scripts.")

        control = is_control_statement(stmt_tokens)
        statements.append(
            LocalStatement(
                statement_index=index,
                is_control=control,
                start_line=raw.span.start_line,
                end_line=raw.span.end_line,
                tokens=stmt_tokens,
                statement_fingerprint=statement_fingerprint(stmt_tokens),
                sanitized_preview=sanitized_preview(stmt_tokens),
            )
        )
        if control:
            control_ordinals.append(index)
        else:
            has_analyzable_statement = True

    if not has_analyzable_statement:
        raise LocalPhaseError("No analyzable DDL statements.")

    return LocalParsedScript(
        path_basename=loaded.path_basename,
        statements=tuple(statements),
        control_ordinals=tuple(control_ordinals),
        source_statement_count=len(statements),
    )
