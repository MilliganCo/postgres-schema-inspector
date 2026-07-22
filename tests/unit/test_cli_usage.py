"""CLI usage-error catalog and option surface tests."""

from __future__ import annotations

import click
import pytest

from pginspect.cli import (
    CliErrorCode,
    CommandRequiredError,
    UnknownCommandError,
    classify_usage_error,
    main,
)


def test_empty_argv_returns_4(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 4
    captured = capsys.readouterr()
    assert "A command is required." in captured.err
    assert captured.out == ""


def test_root_format_returns_4(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--format", "json", "version"]) == 4
    err = capsys.readouterr().err
    assert err.strip() == "Unknown option."
    assert "json" not in err
    assert "version" not in err or err.strip() == "Unknown option."


def test_port_abc_returns_4_without_echoing_value(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["connect-test", "--port", "abc"])
    assert code == 4
    err = capsys.readouterr().err
    assert "abc" not in err
    assert "Invalid value for --port." in err


def test_unknown_command_does_not_echo_token(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["totally-unknown-cmd"]) == 4
    err = capsys.readouterr().err
    assert "totally-unknown-cmd" not in err
    assert err.strip() == "Unknown command."


def test_missing_port_value(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["connect-test", "--port"]) == 4
    err = capsys.readouterr().err
    assert err.strip() == "Missing value for --port."


def test_lock_timeout_config_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "connect-test",
            "--statement-timeout",
            "1000",
            "--lock-timeout",
            "1000",
        ]
    )
    assert code == 4
    err = capsys.readouterr().err
    assert "lock_timeout must be less than statement_timeout." in err


def test_version_help_exit_0() -> None:
    assert main(["--help"]) == 0
    assert main(["version", "--help"]) == 0
    assert main(["connect-test", "--help"]) == 0


def test_root_help_has_help_not_short_h(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "--help" in out
    assert "-h," not in out
    assert "version" in out
    assert "connect-test" in out


def test_connect_test_help_uses_h_for_host(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["connect-test", "--help"]) == 0
    out = capsys.readouterr().out
    assert "-h, --host" in out
    assert "--password" not in out
    assert "-W" not in out or "-W," not in out
    assert "--dsn" not in out


def test_no_completion_options_in_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "--install-completion" not in out
    assert "--show-completion" not in out


def test_classify_usage_error_catalog() -> None:
    code, message = classify_usage_error(CommandRequiredError("A command is required.", None))
    assert code is CliErrorCode.COMMAND_REQUIRED
    assert message == "A command is required."

    code, message = classify_usage_error(UnknownCommandError("Unknown command.", None))
    assert code is CliErrorCode.UNKNOWN_COMMAND
    assert message == "Unknown command."

    code, message = classify_usage_error(click.NoSuchOption("--format"))
    assert code is CliErrorCode.UNKNOWN_OPTION
    assert message == "Unknown option."
