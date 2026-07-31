#!/usr/bin/env python3
"""Export Pydantic public models to committed JSON Schema files."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from pginspect.impact.models.card import ImpactStatementCard
from pginspect.impact.models.result import ImpactCommandResult
from pginspect.models.finding import Finding
from pginspect.models.result import CommandResult

ROOT = Path(__file__).resolve().parents[1]

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"

FINDING_SCHEMA_ID = "urn:pginspect:schema:finding:1.0"
COMMAND_RESULT_SCHEMA_ID = "urn:pginspect:schema:command-result:1.0"
IMPACT_COMMAND_RESULT_SCHEMA_ID = "urn:pginspect:schema:impact-command-result:0.1"
IMPACT_STATEMENT_CARD_SCHEMA_ID = "urn:pginspect:schema:impact-statement-card:0.1"

FINDING_SCHEMA_PATH = ROOT / "docs" / "schemas" / "finding" / "1.0.schema.json"
COMMAND_RESULT_SCHEMA_PATH = ROOT / "docs" / "schemas" / "command-result" / "1.0.schema.json"
IMPACT_COMMAND_RESULT_SCHEMA_PATH = (
    ROOT / "docs" / "schemas" / "impact-command-result" / "0.1.schema.json"
)
IMPACT_STATEMENT_CARD_SCHEMA_PATH = (
    ROOT / "docs" / "schemas" / "impact-statement-card" / "0.1.schema.json"
)

EXPECTED_SCHEMA_PATHS: tuple[Path, ...] = (
    FINDING_SCHEMA_PATH,
    COMMAND_RESULT_SCHEMA_PATH,
    IMPACT_COMMAND_RESULT_SCHEMA_PATH,
    IMPACT_STATEMENT_CARD_SCHEMA_PATH,
)


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


def generate_impact_command_result_schema() -> bytes:
    return generate_schema(ImpactCommandResult, IMPACT_COMMAND_RESULT_SCHEMA_ID)


def generate_impact_statement_card_schema() -> bytes:
    return generate_schema(ImpactStatementCard, IMPACT_STATEMENT_CARD_SCHEMA_ID)


def write_schemas(*, root: Path | None = None) -> dict[Path, bytes]:
    """Write all schemas under ``root`` (default: repo ``docs/schemas``).

    Returns a mapping of absolute written paths to bytes.
    """
    base = ROOT if root is None else root
    mapping: dict[Path, bytes] = {
        base / "docs" / "schemas" / "finding" / "1.0.schema.json": generate_finding_schema(),
        base
        / "docs"
        / "schemas"
        / "command-result"
        / "1.0.schema.json": generate_command_result_schema(),
        base
        / "docs"
        / "schemas"
        / "impact-command-result"
        / "0.1.schema.json": generate_impact_command_result_schema(),
        base
        / "docs"
        / "schemas"
        / "impact-statement-card"
        / "0.1.schema.json": generate_impact_statement_card_schema(),
    }
    for path, payload in mapping.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return mapping


def main() -> int:
    written = write_schemas()
    for path in written:
        print(f"Wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
