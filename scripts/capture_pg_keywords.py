#!/usr/bin/env python3
"""Capture `pg_get_keywords()` word -> catcode fixtures for a specific major.

Dev helper for `tests/fixtures/impact/keywords/pgNN.json` (plan Task 3). Not
part of the shipped package: reads only `PGINSPECT_TEST_DSN` from the
environment (never a `--dsn`/`--password` flag) and may import `psycopg`
directly, unlike `src/pginspect/impact/**`.

Usage:
    python scripts/capture_pg_keywords.py --major 16 --out tests/fixtures/impact/keywords/pg16.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg


def _connect_dsn() -> str:
    dsn = os.environ.get("PGINSPECT_TEST_DSN")
    if not dsn:
        raise SystemExit("PGINSPECT_TEST_DSN must be set in the environment.")
    return dsn


def capture_keywords(dsn: str, expected_major: int) -> dict[str, str]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT current_setting('server_version_num')::int")
        row = cur.fetchone()
        if row is None:
            raise SystemExit("Could not read server_version_num.")
        server_version_num = int(row[0])
        actual_major = server_version_num // 10000
        if actual_major != expected_major:
            raise SystemExit(
                f"Connected server major {actual_major} does not match "
                f"requested --major {expected_major}."
            )

        cur.execute("SELECT word, catcode FROM pg_catalog.pg_get_keywords() ORDER BY word")
        return {word: catcode for word, catcode in cur.fetchall()}


def write_keywords_json(keywords: dict[str, str], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = dict(sorted(keywords.items()))
    out_path.write_text(json.dumps(ordered, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--major", type=int, required=True, help="Expected PostgreSQL major version."
    )
    parser.add_argument("--out", type=Path, required=True, help="Output JSON path.")
    args = parser.parse_args(argv)

    dsn = _connect_dsn()
    keywords = capture_keywords(dsn, args.major)
    write_keywords_json(keywords, args.out)
    print(f"Wrote {len(keywords)} keywords for major {args.major} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
