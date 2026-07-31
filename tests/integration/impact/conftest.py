"""Shared helpers for impact live integration tests."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.impact.models.result import ImpactCommandResult
from pginspect.impact.run import run_impact

from tests.integration.impact._fixture_admin import (
    apply_setup_sql,
    drop_fixture_schemas,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "impact"

DEMO_FIXTURE_IDS: tuple[str, ...] = (
    "T1",
    "T2",
    "T3",
    "A1",
    "A2",
    "A3",
    "A4",
    "A5",
    "D1",
    "D2",
    "D3",
    "X1",
)

SEMANTIC_CARD_KEYS: tuple[str, ...] = (
    "analysis_status",
    "execution_prediction",
    "table_rewrite",
    "table_scan",
    "index_rebuild",
    "lock",
    "risk",
    "evidence_ids",
    "limitations_contains",
    "no_op_reason",
)


def fixture_dir(fixture_id: str) -> Path:
    return FIXTURE_ROOT / fixture_id


def deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = copy.deepcopy(base)
        for key, value in overlay.items():
            if key in out:
                out[key] = deep_merge(out[key], value)
            else:
                out[key] = copy.deepcopy(value)
        return out
    if isinstance(base, list) and isinstance(overlay, list):
        out_list = copy.deepcopy(base)
        for index, value in enumerate(overlay):
            if index < len(out_list):
                out_list[index] = deep_merge(out_list[index], value)
            else:
                out_list.append(copy.deepcopy(value))
        return out_list
    return copy.deepcopy(overlay)


def load_expected(fixture_id: str, major: int) -> dict[str, Any]:
    expected_dir = fixture_dir(fixture_id) / "expected"
    common = json.loads((expected_dir / "common.json").read_text(encoding="utf-8"))
    overlay_path = expected_dir / f"pg{major}.json"
    if overlay_path.is_file():
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        return deep_merge(common, overlay)
    return common


def project_card(card: Any) -> dict[str, Any]:
    evidence_ids = list(card.evidence_refs)
    limitations = list(card.limitations)
    projected: dict[str, Any] = {
        "analysis_status": card.analysis_status.value,
        "execution_prediction": card.execution_prediction.value,
        "table_rewrite": card.table_rewrite.value,
        "table_scan": card.table_scan.value,
        "index_rebuild": card.index_rebuild.value,
        "lock": card.lock.value,
        "risk": card.risk.value,
        "evidence_ids": evidence_ids,
        "limitations": limitations,
        "no_op_reason": None if card.no_op_reason is None else card.no_op_reason.value,
    }
    return projected


def assert_expected_projection(result: ImpactCommandResult, expected: Mapping[str, Any]) -> None:
    assert result.outcome.value == expected["outcome"]
    assert result.exit_code == expected["exit_code"]
    expected_cards = expected["cards"]
    assert len(result.statements) == len(expected_cards)
    for card, exp in zip(result.statements, expected_cards, strict=True):
        projected = project_card(card)
        if "analysis_status" in exp:
            assert projected["analysis_status"] == exp["analysis_status"]
        if "execution_prediction" in exp:
            assert projected["execution_prediction"] == exp["execution_prediction"]
        if "table_rewrite" in exp:
            assert projected["table_rewrite"] == exp["table_rewrite"]
        if "table_scan" in exp:
            assert projected["table_scan"] == exp["table_scan"]
        if "index_rebuild" in exp:
            assert projected["index_rebuild"] == exp["index_rebuild"]
        if "lock" in exp:
            assert projected["lock"] == exp["lock"]
        if "risk" in exp:
            assert projected["risk"] == exp["risk"]
        if "no_op_reason" in exp:
            assert projected["no_op_reason"] == exp["no_op_reason"]
        if "evidence_ids" in exp:
            for evidence_id in exp["evidence_ids"]:
                assert evidence_id in projected["evidence_ids"], (
                    f"missing evidence {evidence_id!r} in {projected['evidence_ids']}"
                )
        if "limitations_contains" in exp:
            for limitation in exp["limitations_contains"]:
                assert limitation in projected["limitations"], f"missing limitation {limitation!r}"


def semantic_projection(result: ImpactCommandResult) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    for card in result.statements:
        projected = project_card(card)
        slim = {
            "analysis_status": projected["analysis_status"],
            "execution_prediction": projected["execution_prediction"],
            "table_rewrite": projected["table_rewrite"],
            "table_scan": projected["table_scan"],
            "index_rebuild": projected["index_rebuild"],
            "lock": projected["lock"],
            "risk": projected["risk"],
            "evidence_ids": projected["evidence_ids"],
            "limitations_contains": [
                limitation
                for limitation in (
                    "Table emptiness is not proven from catalog evidence "
                    "(n_live_tup is an estimate).",
                    "Authorization failures are not modeled; analysis assumes "
                    "sufficient privileges.",
                )
                if limitation in projected["limitations"]
            ],
        }
        cards.append(slim)
    return {
        "outcome": result.outcome.value,
        "exit_code": result.exit_code,
        "cards": cards,
    }


def run_fixture(
    fixture_id: str,
    *,
    admin_dsn: str,
    connection_config: ConnectionConfig,
    session_safety: SessionSafetyConfig | None = None,
) -> ImpactCommandResult:
    path = fixture_dir(fixture_id)
    apply_setup_sql(admin_dsn, path / "setup.sql")
    try:
        return run_impact(
            path / "migration.sql",
            connection_config,
            session_safety or SessionSafetyConfig(),
        )
    finally:
        drop_fixture_schemas(admin_dsn, fixture_id)


@contextmanager
def subject_env_scs_off() -> Iterator[None]:
    previous = os.environ.get("PGOPTIONS")
    os.environ["PGOPTIONS"] = "-c standard_conforming_strings=off"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = previous


@contextmanager
def subject_env_search_path(search_path: str) -> Iterator[None]:
    previous = os.environ.get("PGOPTIONS")
    # No spaces: libpq PGOPTIONS tokenization is fragile with commas+spaces.
    compact = ",".join(part.strip() for part in search_path.split(","))
    os.environ["PGOPTIONS"] = f"-c search_path={compact}"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = previous


@pytest.fixture
def impact_session_safety() -> SessionSafetyConfig:
    return SessionSafetyConfig()


@pytest.fixture
def admin_dsn(pg_dsn: str) -> str:
    return pg_dsn


@pytest.fixture
def server_major(pg_dsn: str, _apply_probe_fixture: None) -> int:
    import psycopg

    with psycopg.connect(pg_dsn) as conn:
        version_num = int(conn.execute("SHOW server_version_num").fetchone()[0])
    return version_num // 10000
