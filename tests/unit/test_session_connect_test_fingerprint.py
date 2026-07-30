"""Golden fingerprint guard: connect-test establish/verify SQL must not drift."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pginspect import session as s

_GOLDEN_PATH = Path("tests/unit/goldens/session_sql_hashes.json")


def test_connect_test_establish_sql_unchanged() -> None:
    expected = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    assert (
        hashlib.sha256(s._ESTABLISH_SQL.encode("utf-8")).hexdigest()
        == expected["establish_sql_sha256"]
    )
    assert (
        hashlib.sha256(s._VERIFY_SQL.encode("utf-8")).hexdigest() == expected["verify_sql_sha256"]
    )
