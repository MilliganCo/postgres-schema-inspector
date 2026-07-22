#!/usr/bin/env python3
"""Export Pydantic public models to committed JSON Schema files."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from pginspect.models.finding import Finding
from pginspect.models.result import CommandResult

ROOT = Path(__file__).resolve().parents[1]

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"

FINDING_SCHEMA_ID = "urn:pginspect:schema:finding:1.0"
COMMAND_RESULT_SCHEMA_ID = "urn:pginspect:schema:command-result:1.0"

FINDING_SCHEMA_PATH = ROOT / "docs" / "schemas" / "finding" / "1.0.schema.json"
COMMAND_RESULT_SCHEMA_PATH = ROOT / "docs" / "schemas" / "command-result" / "1.0.schema.json"


def canonical_schema_bytes(schema: dict[str, Any]) -> bytes:
    return (json.dumps(schema, indent=2, sort_keys=True) + "\n").encode("utf-8")


def generate_schema(model: type[Any], schema_id: str) -> bytes:
    schema = TypeAdapter(model).json_schema(mode="serialization")
    schema["$schema"] = SCHEMA_DRAFT
    schema["$id"] = schema_id
    return canonical_schema_bytes(schema)


def generate_finding_schema() -> bytes:
    return generate_schema(Finding, FINDING_SCHEMA_ID)


def generate_command_result_schema() -> bytes:
    return generate_schema(CommandResult, COMMAND_RESULT_SCHEMA_ID)


def write_schemas() -> None:
    FINDING_SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMMAND_RESULT_SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    FINDING_SCHEMA_PATH.write_bytes(generate_finding_schema())
    COMMAND_RESULT_SCHEMA_PATH.write_bytes(generate_command_result_schema())


def main() -> int:
    write_schemas()
    print(f"Wrote {FINDING_SCHEMA_PATH.relative_to(ROOT)}")
    print(f"Wrote {COMMAND_RESULT_SCHEMA_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
