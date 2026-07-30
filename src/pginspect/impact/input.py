"""Local file loader for migration scripts (design section 1.1).

Only this module performs filesystem I/O for the migration path. `run_impact`,
the CLI, and every other component receive already-loaded/parsed data and
never touch `Path.open`/`stat` for the migration file themselves.

Public metadata is `path_basename` only: `LocalPhaseError.public_message`
must never contain the full filesystem path or raw SQL text.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from pginspect.impact.parser.ast import MAX_FILE_SIZE_BYTES

_UTF8_BOM = b"\xef\xbb\xbf"


class LocalPhaseError(Exception):
    """Raised for every local/lexical migration-loading failure (process exit 4).

    `public_message` never contains the full filesystem path or raw SQL text.
    """

    def __init__(self, public_message: str) -> None:
        self.public_message = public_message
        super().__init__(public_message)


@dataclass(frozen=True)
class LoadedMigrationSource:
    path_basename: str
    text: str


def load_migration_source(path: Path) -> LoadedMigrationSource:
    """Open once (binary), fstat, enforce limits, decode strict UTF-8, strip BOM."""
    if os.fspath(path) == "-":
        raise LocalPhaseError("Reading the migration from stdin ('-') is not supported.")

    path_basename = path.name

    try:
        file_handle = path.open("rb")
    except OSError as exc:
        raise LocalPhaseError(f"Cannot open migration file {path_basename!r}.") from exc

    try:
        with file_handle:
            file_stat = os.fstat(file_handle.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise LocalPhaseError(f"Migration path {path_basename!r} is not a regular file.")
            if file_stat.st_size > MAX_FILE_SIZE_BYTES:
                raise LocalPhaseError(
                    f"Migration file {path_basename!r} exceeds the maximum supported size."
                )
            raw_bytes = file_handle.read(MAX_FILE_SIZE_BYTES + 1)
    except OSError as exc:
        raise LocalPhaseError(f"Cannot read migration file {path_basename!r}.") from exc

    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise LocalPhaseError(
            f"Migration file {path_basename!r} exceeds the maximum supported size."
        )

    if raw_bytes.startswith(_UTF8_BOM):
        raw_bytes = raw_bytes[len(_UTF8_BOM) :]

    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise LocalPhaseError(f"Migration file {path_basename!r} is not valid UTF-8.") from exc

    return LoadedMigrationSource(path_basename=path_basename, text=text)
