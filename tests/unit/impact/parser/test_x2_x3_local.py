"""X2/X3 local-only fixtures plus general `parse_migration_path` behavior (Task 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pginspect.impact.parse_local import LocalPhaseError, parse_migration_path

_FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "impact"


def test_local_parsed_script_counts_controls(tmp_path: Path) -> None:
    p = tmp_path / "m.sql"
    p.write_text("BEGIN;\nALTER TABLE t ADD COLUMN a int;\nCOMMIT;\n", encoding="utf-8")
    script = parse_migration_path(p)
    assert script.source_statement_count == 3
    assert script.control_ordinals == (1, 3)
    assert len([s for s in script.statements if not s.is_control]) == 1


def test_local_statement_carries_tokens_fingerprint_and_preview(tmp_path: Path) -> None:
    p = tmp_path / "m.sql"
    p.write_text("ALTER TABLE t ADD COLUMN a int;\n", encoding="utf-8")
    script = parse_migration_path(p)
    (stmt,) = script.statements
    assert stmt.tokens
    assert stmt.statement_fingerprint.startswith("sha256:")
    assert stmt.sanitized_preview == "ALTER TABLE t ADD COLUMN a int"


def test_x2_unclosed_string_is_rejected() -> None:
    with pytest.raises(LocalPhaseError):
        parse_migration_path(_FIXTURES_ROOT / "X2" / "migration.sql")


def test_x3_comment_only_is_rejected() -> None:
    with pytest.raises(LocalPhaseError):
        parse_migration_path(_FIXTURES_ROOT / "X3" / "migration.sql")


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    p = tmp_path / "empty.sql"
    p.write_text("", encoding="utf-8")
    with pytest.raises(LocalPhaseError):
        parse_migration_path(p)


def test_only_semicolons_is_rejected(tmp_path: Path) -> None:
    p = tmp_path / "only_semicolons.sql"
    p.write_text(";;;\n", encoding="utf-8")
    with pytest.raises(LocalPhaseError):
        parse_migration_path(p)


def test_only_control_statements_is_rejected_with_exact_message(tmp_path: Path) -> None:
    p = tmp_path / "only_control.sql"
    p.write_text("BEGIN;\nCOMMIT;\n", encoding="utf-8")
    with pytest.raises(LocalPhaseError) as exc_info:
        parse_migration_path(p)
    assert exc_info.value.public_message == "No analyzable DDL statements."


def test_copy_from_stdin_with_inline_payload_is_rejected(tmp_path: Path) -> None:
    p = tmp_path / "copy.sql"
    p.write_text(
        "COPY t (a, b) FROM STDIN;\n1\tone\n2\ttwo\n\\.\n",
        encoding="utf-8",
    )
    with pytest.raises(LocalPhaseError):
        parse_migration_path(p)


def test_copy_from_stdin_without_payload_is_rejected(tmp_path: Path) -> None:
    p = tmp_path / "copy_bare.sql"
    p.write_text("COPY t (a, b) FROM STDIN;\n", encoding="utf-8")
    with pytest.raises(LocalPhaseError):
        parse_migration_path(p)


def test_statement_indexes_are_one_based_and_ascending(tmp_path: Path) -> None:
    p = tmp_path / "m.sql"
    p.write_text(
        "ALTER TABLE t ADD COLUMN a int;\nALTER TABLE t ADD COLUMN b int;\n",
        encoding="utf-8",
    )
    script = parse_migration_path(p)
    assert [s.statement_index for s in script.statements] == [1, 2]


def test_path_basename_only_never_full_path(tmp_path: Path) -> None:
    nested = tmp_path / "some_secret_directory_name"
    nested.mkdir()
    p = nested / "migration.sql"
    p.write_text("ALTER TABLE t ADD COLUMN a int;\n", encoding="utf-8")
    script = parse_migration_path(p)
    assert script.path_basename == "migration.sql"


def test_statement_count_over_limit_raises_local_phase_error(tmp_path: Path) -> None:
    p = tmp_path / "many.sql"
    p.write_text("SELECT 1;" * 1001, encoding="utf-8")
    with pytest.raises(LocalPhaseError):
        parse_migration_path(p)


def test_canary_absent_from_script_previews_and_fingerprints(tmp_path: Path) -> None:
    canary = "CANARY_SECRET_7f03"
    p = tmp_path / "m.sql"
    p.write_text(f"ALTER TABLE t ADD COLUMN x text DEFAULT '{canary}';\n", encoding="utf-8")
    script = parse_migration_path(p)
    (stmt,) = script.statements
    assert canary not in stmt.sanitized_preview
    assert canary not in stmt.statement_fingerprint
    assert all(canary not in tok.normalized for tok in stmt.tokens)
