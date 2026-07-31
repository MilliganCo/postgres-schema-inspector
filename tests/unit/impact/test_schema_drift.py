"""Impact 0.1 schema drift and golden round-trip checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema.validators import Draft202012Validator
from pydantic import TypeAdapter

from pginspect.impact.models.card import ImpactStatementCard
from pginspect.impact.models.result import ImpactCommandResult, impact_command_result_adapter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from export_schemas import (  # noqa: E402
    IMPACT_COMMAND_RESULT_SCHEMA_ID,
    IMPACT_COMMAND_RESULT_SCHEMA_PATH,
    IMPACT_STATEMENT_CARD_SCHEMA_ID,
    IMPACT_STATEMENT_CARD_SCHEMA_PATH,
    generate_impact_command_result_schema,
    generate_impact_statement_card_schema,
)

GOLDENS_DIR = ROOT / "tests" / "schemas" / "goldens"


def test_committed_impact_command_result_schema_matches_generated() -> None:
    assert IMPACT_COMMAND_RESULT_SCHEMA_PATH.read_bytes() == (
        generate_impact_command_result_schema()
    )


def test_committed_impact_statement_card_schema_matches_generated() -> None:
    assert IMPACT_STATEMENT_CARD_SCHEMA_PATH.read_bytes() == (
        generate_impact_statement_card_schema()
    )


def test_committed_impact_schemas_declare_draft_and_ids() -> None:
    command_result = json.loads(IMPACT_COMMAND_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    statement_card = json.loads(IMPACT_STATEMENT_CARD_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert command_result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert command_result["$id"] == IMPACT_COMMAND_RESULT_SCHEMA_ID
    assert statement_card["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert statement_card["$id"] == IMPACT_STATEMENT_CARD_SCHEMA_ID


def _impact_command_result_validator() -> Draft202012Validator:
    schema = json.loads(IMPACT_COMMAND_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _impact_statement_card_validator() -> Draft202012Validator:
    schema = json.loads(IMPACT_STATEMENT_CARD_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize(
    "path",
    sorted(GOLDENS_DIR.glob("impact_*.json")),
    ids=lambda p: p.name,
)
def test_impact_golden_fixtures_validate_and_round_trip(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    _impact_command_result_validator().validate(raw)
    model = impact_command_result_adapter.validate_python(raw)
    dumped = TypeAdapter(ImpactCommandResult).dump_python(model, mode="json")
    assert dumped == raw


def test_impact_statement_card_schema_validates_embedded_card() -> None:
    payload = json.loads(
        (GOLDENS_DIR / "impact_completed_warning.json").read_text(encoding="utf-8")
    )
    card_raw = payload["statements"][0]
    _impact_statement_card_validator().validate(card_raw)
    model = TypeAdapter(ImpactStatementCard).validate_python(card_raw)
    dumped = TypeAdapter(ImpactStatementCard).dump_python(model, mode="json")
    assert dumped == card_raw
