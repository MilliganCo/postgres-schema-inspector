#!/usr/bin/env python3
"""Compare a fresh schema export against committed docs/schemas bytes."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_schemas import (  # noqa: E402
    COMMAND_RESULT_SCHEMA_PATH,
    EXPECTED_SCHEMA_PATHS,
    FINDING_SCHEMA_PATH,
    IMPACT_COMMAND_RESULT_SCHEMA_PATH,
    IMPACT_STATEMENT_CARD_SCHEMA_PATH,
    write_schemas,
)

FOUNDATION_PATHS = (FINDING_SCHEMA_PATH, COMMAND_RESULT_SCHEMA_PATH)
IMPACT_PATHS = (IMPACT_COMMAND_RESULT_SCHEMA_PATH, IMPACT_STATEMENT_CARD_SCHEMA_PATH)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    errors: list[str] = []

    for path in EXPECTED_SCHEMA_PATHS:
        if not path.is_file():
            errors.append(f"missing committed schema: {_rel(path)}")

    with tempfile.TemporaryDirectory(prefix="pginspect-schemas-") as tmp:
        temp_root = Path(tmp)
        written = write_schemas(root=temp_root)
        expected_rel = {path.relative_to(ROOT).as_posix() for path in EXPECTED_SCHEMA_PATHS}
        produced_rel = {path.relative_to(temp_root).as_posix() for path in written}
        unexpected = sorted(produced_rel - expected_rel)
        missing_generated = sorted(expected_rel - produced_rel)
        if unexpected:
            errors.append(f"unexpected generated schema paths: {unexpected}")
        if missing_generated:
            errors.append(f"export missed expected schema paths: {missing_generated}")

        for committed in EXPECTED_SCHEMA_PATHS:
            generated = temp_root / committed.relative_to(ROOT)
            if not committed.is_file() or not generated.is_file():
                continue
            committed_bytes = committed.read_bytes()
            generated_bytes = generated.read_bytes()
            if committed_bytes != generated_bytes:
                kind = (
                    "Foundation 1.0"
                    if committed in FOUNDATION_PATHS
                    else "impact 0.1"
                    if committed in IMPACT_PATHS
                    else "schema"
                )
                errors.append(f"{kind} drift: {_rel(committed)} differs from fresh export")

    if errors:
        for item in errors:
            print(f"ERROR: {item}", file=sys.stderr)
        return 1

    print("schema export compare OK")
    for path in EXPECTED_SCHEMA_PATHS:
        print(f"  {_rel(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
