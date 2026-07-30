"""Tests for `pginspect.impact.input` — local file loader (design section 1.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pginspect.impact.input import LocalPhaseError, load_migration_source
from pginspect.impact.parser.ast import MAX_FILE_SIZE_BYTES


def test_loads_utf8_text_and_strips_bom(tmp_path: Path) -> None:
    p = tmp_path / "m.sql"
    p.write_bytes(b"\xef\xbb\xbfSELECT 1;\n")
    loaded = load_migration_source(p)
    assert loaded.path_basename == "m.sql"
    assert loaded.text == "SELECT 1;\n"


def test_loads_plain_utf8_without_bom(tmp_path: Path) -> None:
    p = tmp_path / "m.sql"
    p.write_bytes("SELECT 1;\n".encode("utf-8"))
    loaded = load_migration_source(p)
    assert loaded.text == "SELECT 1;\n"


def test_rejects_stdin_dash() -> None:
    with pytest.raises(LocalPhaseError):
        load_migration_source(Path("-"))


def test_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(LocalPhaseError):
        load_migration_source(tmp_path)


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LocalPhaseError):
        load_migration_source(tmp_path / "does-not-exist.sql")


def test_rejects_oversized_file(tmp_path: Path) -> None:
    p = tmp_path / "big.sql"
    p.write_bytes(b"-" * (MAX_FILE_SIZE_BYTES + 1))
    with pytest.raises(LocalPhaseError):
        load_migration_source(p)


def test_accepts_file_at_exact_size_limit(tmp_path: Path) -> None:
    p = tmp_path / "exact.sql"
    padding = b"-" * (MAX_FILE_SIZE_BYTES - len(b"SELECT 1;\n"))
    p.write_bytes(padding + b"SELECT 1;\n")
    loaded = load_migration_source(p)
    assert loaded.text.endswith("SELECT 1;\n")


def test_rejects_invalid_utf8(tmp_path: Path) -> None:
    p = tmp_path / "bad.sql"
    p.write_bytes(b"SELECT '\xff';")
    with pytest.raises(LocalPhaseError):
        load_migration_source(p)


def test_error_message_never_contains_full_path(tmp_path: Path) -> None:
    nested = tmp_path / "secret_dir_name"
    nested.mkdir()
    p = nested / "migration.sql"
    p.write_bytes(b"\xff\xfe")
    with pytest.raises(LocalPhaseError) as exc_info:
        load_migration_source(p)
    assert str(nested) not in exc_info.value.public_message
    assert "migration.sql" in exc_info.value.public_message
