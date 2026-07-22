"""Architecture boundary tests (Spec §12)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "pginspect"


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _module_name(path: Path) -> str:
    rel = path.relative_to(SRC_ROOT.parent)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
                names.add(node.module)
    return names


def _read_tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_only_connection_and_session_import_psycopg() -> None:
    offenders: list[str] = []
    for path in _iter_python_files(SRC_ROOT):
        tree = _read_tree(path)
        imported = _imported_modules(tree)
        if "psycopg" not in imported and not any(n.startswith("psycopg.") for n in imported):
            continue
        mod = _module_name(path)
        if mod not in {"pginspect.connection", "pginspect.session"}:
            offenders.append(mod)
    assert offenders == [], f"psycopg imported outside connection/session: {offenders}"


def test_cli_has_no_sql_and_no_psycopg() -> None:
    path = SRC_ROOT / "cli.py"
    source = path.read_text(encoding="utf-8")
    tree = _read_tree(path)
    imported = _imported_modules(tree)
    assert "psycopg" not in imported
    assert not any(n.startswith("psycopg.") for n in imported)
    # No SQL string literals that look like statements.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.strip().lower()
            assert not lowered.startswith("select ")
            assert not lowered.startswith("insert ")
            assert "set_config" not in lowered
    assert "SELECT" not in source
    assert "set_config" not in source


def test_renderers_do_not_import_connection_session_connectivity() -> None:
    forbidden_roots = {
        "pginspect.connection",
        "pginspect.session",
        "pginspect.connectivity",
        "connection",
        "session",
        "connectivity",
    }
    renderers_root = SRC_ROOT / "renderers"
    for path in _iter_python_files(renderers_root):
        imported = _imported_modules(_read_tree(path))
        bad = imported & forbidden_roots
        assert not bad, f"{path.name} imports {bad}"
        for name in imported:
            assert not name.startswith("pginspect.connection")
            assert not name.startswith("pginspect.session")
            assert not name.startswith("pginspect.connectivity")


def test_models_import_no_io_typer_rich_or_psycopg() -> None:
    forbidden = {"typer", "rich", "psycopg", "click", "sys", "socket", "http", "urllib", "requests"}
    models_root = SRC_ROOT / "models"
    for path in _iter_python_files(models_root):
        imported = _imported_modules(_read_tree(path))
        # Top-level package names only for this check.
        top = {n.split(".")[0] for n in imported}
        hit = top & forbidden
        assert not hit, f"{path.name} imports forbidden modules: {hit}"


def test_no_src_module_calls_sys_exit() -> None:
    offenders: list[str] = []
    for path in _iter_python_files(SRC_ROOT):
        tree = _read_tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "exit":
                    if isinstance(func.value, ast.Name) and func.value.id == "sys":
                        offenders.append(_module_name(path))
                if isinstance(func, ast.Name) and func.id == "exit":
                    offenders.append(_module_name(path))
    assert offenders == [], f"sys.exit/exit used in: {offenders}"


def test_no_production_public_execute_query() -> None:
    """No production module exposes arbitrary public execute(query)."""
    offenders: list[str] = []
    for path in _iter_python_files(SRC_ROOT):
        tree = _read_tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "execute":
                # Package-private helpers are allowed only with leading underscore.
                if not node.name.startswith("_"):
                    # Allow nested/local? Only module-level or class methods named execute.
                    offenders.append(f"{_module_name(path)}:execute")
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute":
                offenders.append(f"{_module_name(path)}:async execute")
    assert offenders == [], f"public execute() found: {offenders}"


def test_no_production_module_reads_pgpassword_or_pgpassfile() -> None:
    markers = ("PGPASSWORD", "PGPASSFILE")
    offenders: list[str] = []
    for path in _iter_python_files(SRC_ROOT):
        source = path.read_text(encoding="utf-8")
        tree = _read_tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in markers:
                    offenders.append(_module_name(path))
        # Also catch bare names in source for defense-in-depth on getenv usage patterns.
        if 'getenv("PGPASSWORD")' in source or "getenv('PGPASSWORD')" in source:
            offenders.append(_module_name(path))
        if 'getenv("PGPASSFILE")' in source or "getenv('PGPASSFILE')" in source:
            offenders.append(_module_name(path))
        if 'environ["PGPASSWORD"]' in source or "environ['PGPASSWORD']" in source:
            offenders.append(_module_name(path))
    assert offenders == [], f"PGPASSWORD/PGPASSFILE read in: {sorted(set(offenders))}"


def test_no_sql_constants_in_cli_or_renderers() -> None:
    targets = [SRC_ROOT / "cli.py", *(_iter_python_files(SRC_ROOT / "renderers"))]
    sql_markers = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "set_config(", "FROM pg_")
    for path in targets:
        source = path.read_text(encoding="utf-8")
        for marker in sql_markers:
            assert marker not in source, f"{path} contains SQL marker {marker!r}"


def test_absent_deferred_packages_and_modules() -> None:
    forbidden_dirs = {"checks", "actions", "plans", "plugins", "profiles", "sql"}
    present = {p.name for p in SRC_ROOT.iterdir() if p.is_dir()}
    assert not (present & forbidden_dirs)
    assert not (SRC_ROOT / "doctor.py").exists()


@pytest.mark.parametrize(
    "forbidden",
    ["checks", "actions", "plans", "plugins", "profiles", "sql", "doctor"],
)
def test_no_deferred_top_level_imports(forbidden: str) -> None:
    for path in _iter_python_files(SRC_ROOT):
        imported = _imported_modules(_read_tree(path))
        assert f"pginspect.{forbidden}" not in imported
        assert not any(n.startswith(f"pginspect.{forbidden}.") for n in imported)
