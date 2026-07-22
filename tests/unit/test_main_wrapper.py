"""Wrapper-level tests for ``main()`` exit-code mapping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pginspect.cli import main
from pginspect.connectivity import build_version_result
from pginspect.models.enums import CommandExitCode


def test_version_returns_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("pginspect ")
    assert out.endswith("\n")
    assert "Exit:" not in out


def test_version_json_returns_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version", "--format", "json"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert captured.out.endswith("\n")
    assert '"command": "version"' in captured.out
    assert captured.err == ""


def test_keyboard_interrupt_returns_130() -> None:
    with patch("pginspect.cli.get_command") as get_command:
        command = MagicMock()
        get_command.return_value = command
        command.make_context.side_effect = KeyboardInterrupt()
        assert main(["version"]) == 130


def test_connect_test_returns_result_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    result = build_version_result()  # placeholder shape unused
    # Build a fake connect-test result via mock of run_connect_test
    fake = MagicMock()
    fake.exit_code = CommandExitCode.OPERATIONAL_FAILURE
    fake.command = "connect-test"
    with (
        patch("pginspect.cli.run_connect_test", return_value=fake) as mocked,
        patch("pginspect.cli.render_text", return_value="Connection: failed\n"),
        patch("pginspect.cli.render_text_debug", return_value=None),
    ):
        code = main(["connect-test", "--host", "db.example"])
        assert code == 3
        mocked.assert_called_once()
        kwargs = mocked.call_args
        config = kwargs[0][0]
        assert config.connection.host == "db.example"
        assert kwargs.kwargs.get("include_debug") is False
    out = capsys.readouterr().out
    assert out == "Connection: failed\n"


def test_connect_test_json_debug_leaves_stderr_empty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = MagicMock()
    fake.exit_code = CommandExitCode.OK
    with (
        patch("pginspect.cli.run_connect_test", return_value=fake),
        patch("pginspect.cli.render_json", return_value='{"ok": true}\n') as rj,
        patch("pginspect.cli.render_text_debug", return_value="Debug:\n"),
    ):
        assert main(["connect-test", "--format", "json", "--debug"]) == 0
        rj.assert_called_once()
    captured = capsys.readouterr()
    assert captured.out == '{"ok": true}\n'
    assert captured.err == ""


def test_fatal_render_returns_5(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("pginspect.cli.build_version_result", return_value=build_version_result()),
        patch("pginspect.cli.render_text", side_effect=RuntimeError("boom")),
    ):
        assert main(["version"]) == 5
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "pginspect failed due to an internal error." in captured.err
