#!/usr/bin/env python3
"""Record redacted Demo-proof text reports for impact fixtures T1/A4/D2."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from integration.impact._fixture_admin import (  # noqa: E402
    apply_setup_sql,
    drop_schema,
)

EXPECTED_EXIT = {"T1": 2, "A4": 2, "D2": 2}
SCHEMA = {"T1": "impact_t1", "A4": "impact_a4", "D2": "impact_d2"}
FORBIDDEN = ("password=", "PGPASSWORD", ":5432/", "/home/", "C:\\")


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def _verify_recording_major(admin_dsn: str, expected_major: int) -> None:
    import psycopg

    with psycopg.connect(admin_dsn) as conn:
        num = int(conn.execute("SHOW server_version_num").fetchone()[0])
    major = num // 10000
    if major != expected_major:
        raise SystemExit(f"live major {major} != PGINSPECT_RECORDING_MAJOR={expected_major}")


def record_fixture(fixture: str, out_path: Path) -> int:
    if fixture not in EXPECTED_EXIT:
        raise SystemExit(f"unsupported fixture: {fixture}")

    admin_dsn = _require_env("PGINSPECT_TEST_DSN")
    expected_major = int(_require_env("PGINSPECT_RECORDING_MAJOR"))
    _verify_recording_major(admin_dsn, expected_major)

    setup_path = ROOT / "tests" / "fixtures" / "impact" / fixture / "setup.sql"
    migration_path = ROOT / "tests" / "fixtures" / "impact" / fixture / "migration.sql"
    if not setup_path.is_file() or not migration_path.is_file():
        raise SystemExit(f"fixture paths missing for {fixture}")

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_path.with_suffix(out_path.suffix + ".tmp")
    diag_path = out_path.with_suffix(out_path.suffix + ".stderr.txt")

    pginspect = shutil.which("pginspect")
    if pginspect is None:
        raise SystemExit("pginspect executable not found on PATH")

    apply_setup_sql(admin_dsn, setup_path)
    try:
        # Subject connection comes only from libpq env (never argv).
        env = os.environ.copy()
        env.pop("PGOPTIONS", None)
        proc = subprocess.run(
            [pginspect, "impact", str(migration_path), "--format", "text"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
        )
        diag_path.write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != EXPECTED_EXIT[fixture]:
            if tmp_out.exists():
                tmp_out.unlink()
            raise SystemExit(
                f"unexpected exit {proc.returncode} for {fixture}; stderr written to {diag_path}"
            )
        tmp_out.write_text(proc.stdout, encoding="utf-8")
        body = tmp_out.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN:
            if forbidden in body:
                tmp_out.unlink()
                raise SystemExit(f"redaction failed for {fixture}: {forbidden}")
        os.replace(tmp_out, out_path)
        print(
            f"fixture={fixture} major={expected_major}",
            file=sys.stderr,
        )
        return 0
    finally:
        drop_schema(admin_dsn, SCHEMA[fixture])
        if tmp_out.exists():
            tmp_out.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, choices=sorted(EXPECTED_EXIT))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    return record_fixture(args.fixture, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
