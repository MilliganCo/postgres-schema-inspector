"""Committed JSON Schema bytes must match Pydantic serialization export."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema.validators import Draft202012Validator
from pydantic import TypeAdapter

from pginspect.models.finding import finding_adapter
from pginspect.models.result import CommandResult, command_result_adapter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from export_schemas import (  # noqa: E402
    COMMAND_RESULT_SCHEMA_PATH,
    FINDING_SCHEMA_PATH,
    generate_command_result_schema,
    generate_finding_schema,
)

GOLDENS_DIR = ROOT / "tests" / "schemas" / "goldens"


def test_committed_finding_schema_matches_generated() -> None:
    assert FINDING_SCHEMA_PATH.read_bytes() == generate_finding_schema()


def test_committed_command_result_schema_matches_generated() -> None:
    assert COMMAND_RESULT_SCHEMA_PATH.read_bytes() == generate_command_result_schema()


def test_committed_schemas_declare_draft_and_ids() -> None:
    finding = json.loads(FINDING_SCHEMA_PATH.read_text(encoding="utf-8"))
    result = json.loads(COMMAND_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert finding["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert finding["$id"] == "urn:pginspect:schema:finding:1.0"
    assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert result["$id"] == "urn:pginspect:schema:command-result:1.0"


def _command_result_validator() -> Draft202012Validator:
    schema = json.loads(COMMAND_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _finding_validator() -> Draft202012Validator:
    schema = json.loads(FINDING_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize(
    "path",
    sorted(p for p in GOLDENS_DIR.glob("*.json") if not p.name.startswith("impact_")),
    ids=lambda p: p.name,
)
def test_golden_fixtures_validate_and_round_trip(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if path.name.startswith("finding_"):
        _finding_validator().validate(raw)
        model = finding_adapter.validate_python(raw)
        dumped = finding_adapter.dump_python(model, mode="json")
        assert dumped == raw
    else:
        _command_result_validator().validate(raw)
        model = command_result_adapter.validate_python(raw)
        dumped = TypeAdapter(CommandResult).dump_python(model, mode="json")
        # Canonical-equivalent: re-serialize through the same mode.
        assert dumped == raw
