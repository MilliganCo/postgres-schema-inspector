"""CLI tests for the impact command (plan Task 11)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pginspect.cli import main
from pginspect.impact.input import LocalPhaseError
from pginspect.impact.models.enums import Outcome, Risk
from pginspect.impact.models.result import ImpactInputMeta, ImpactPreflight, ImpactSummary


def _fake_result(*, exit_code: int = 1) -> MagicMock:
    fake = MagicMock()
    fake.exit_code = exit_code
    fake.outcome = Outcome.COMPLETED
    fake.command = "impact"
    fake.input = ImpactInputMeta(
        path_basename="migration.sql",
        source_statement_count=1,
        card_count=1,
        control_statement_count=0,
    )
    fake.summary = ImpactSummary(
        overall_risk=Risk.WARNING,
        critical_count=0,
        warning_count=1,
        safe_count=0,
        not_applicable_count=0,
        would_fail_count=0,
        may_fail_count=0,
        unsupported_count=0,
        no_op_count=0,
        analyzed_count=1,
        incomplete=False,
    )
    fake.preflight = ImpactPreflight(
        status="passed",
        analysis_stage_reached="complete",
        checks=(),
        limitations=(),
    )
    fake.error = None
    fake.statements = ()
    fake.evidence = ()
    fake.connection_context = None
    fake.snapshot = None
    fake.model_dump = MagicMock(return_value={"command": "impact", "exit_code": exit_code})
    return fake


def test_impact_help_mentions_impact_and_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["impact", "--help"]) == 0
    out = capsys.readouterr().out
    assert "impact" in out.lower()
    assert "--dsn" not in out
    assert "--password" not in out


def test_installed_entrypoint_help_mentions_impact() -> None:
    from pginspect.cli import main as entry_main

    assert entry_main(["impact", "--help"]) == 0


def test_local_phase_error_exit_4_empty_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    with patch(
        "pginspect.impact.cli.run_impact",
        side_effect=LocalPhaseError("No analyzable DDL statements."),
    ):
        code = main(["impact", "migration.sql", "--host", "db.example"])
    assert code == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "No analyzable DDL statements." in captured.err


def test_json_stdout_one_object_stderr_empty(capsys: pytest.CaptureFixture[str]) -> None:
    fake = _fake_result(exit_code=1)
    payload = {
        "command": "impact",
        "exit_code": 1,
        "input": {"path_basename": "migration.sql"},
    }
    with (
        patch("pginspect.impact.cli.run_impact", return_value=fake),
        patch(
            "pginspect.impact.cli.render_impact_json",
            return_value=json.dumps(payload, indent=2) + "\n",
        ) as rj,
    ):
        assert main(["impact", "mig.sql", "--host", "h", "--format", "json"]) == 1
        rj.assert_called_once()
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.endswith("\n")
    assert json.loads(captured.out)["command"] == "impact"


def test_text_debug_writes_only_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    fake = _fake_result(exit_code=1)
    with (
        patch("pginspect.impact.cli.run_impact", return_value=fake),
        patch("pginspect.impact.cli.render_impact_text", return_value="Impact: completed\n"),
        patch("pginspect.impact.cli.render_impact_text_debug", return_value="Debug:\n  x\n"),
    ):
        assert main(["impact", "mig.sql", "--host", "h", "--debug"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "Impact: completed\n"
    assert captured.err == "Debug:\n  x\n"
    assert "ALTER TABLE" not in captured.out + captured.err


def test_serialization_failure_exit_5_no_result(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = _fake_result()
    with (
        patch("pginspect.impact.cli.run_impact", return_value=fake),
        patch("pginspect.impact.cli.render_impact_text", side_effect=RuntimeError("boom")),
    ):
        assert main(["impact", "mig.sql", "--host", "h"]) == 5
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "pginspect failed due to an internal error." in captured.err


def test_cli_passes_path_without_opening(tmp_path: Path) -> None:
    migration = tmp_path / "deep" / "migration.sql"
    # Do not create the file — CLI must not open/stat it; run_impact is mocked.
    fake = _fake_result(exit_code=0)
    with patch("pginspect.impact.cli.run_impact", return_value=fake) as mocked:
        assert main(["impact", str(migration), "--host", "h", "--format", "text"]) == 0
        passed_path = mocked.call_args[0][0]
        assert Path(passed_path) == migration


def test_no_dsn_or_password_options() -> None:
    from typer.main import get_command

    from pginspect.cli import app

    command = get_command(app)
    impact = command.get_command(command.make_context("pginspect", ["impact"]), "impact")
    opts = {opt for param in impact.params for opt in (param.opts or ())}
    assert "--dsn" not in opts
    assert "--password" not in opts
