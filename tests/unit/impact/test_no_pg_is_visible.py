"""AST/source boundary test: no `pg_*_is_visible` anywhere under impact/*.

After `search_path` is hardened to `pg_catalog`, the visibility helpers
reflect that hardened path and must never be used for name resolution
(design section 2.4). Resolution instead ranks candidates against the
captured `current_schemas(true)` ordering.
"""

from __future__ import annotations

import re
from pathlib import Path

_VISIBILITY_RE = re.compile(r"pg_\w*_is_visible")


def test_source_tree_forbids_all_pg_is_visible() -> None:
    root = Path(__file__).resolve().parents[3] / "src" / "pginspect" / "impact"
    offenders = [
        p for p in root.rglob("*.py") if _VISIBILITY_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
