"""Additional CLI unit coverage: classifiers, config messages, wrapper edges."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import click
import pytest
from pydantic import ValidationError

from pginspect.cli import (
    CliErrorCode,
    _as_usage_error,
    _catalogued_config_message,
    _emit_result,
    _long_option_name,
    classify_usage_error,
    main,
    normalize_command_return,
)
from pginspect.config import ConnectionConfig, SessionSafetyConfig


def test_long_option_name_none_and_fallbacks() -> None:
    assert _long_option_name(None) is None

    short_only = MagicMock()
    short_only.opts = ("-p",)
    short_only.name = "port"
    assert _long_option_name(short_only) == "port"

    empty_name = MagicMock()
    empty_name.opts = ()
    empty_name.name = None
    assert _long_option_name(empty_name) is None

    no_opts = MagicMock()
    no_opts.opts = None
    no_opts.name = "host"
    assert _long_option_name(no_opts) == "host"


def test_classify_missing_parameter_without_param_name() -> None:
    exc = click.MissingParameter(param=None)
    code, message = classify_usage_error(exc)
    assert code is CliErrorCode.MISSING_OPTION_VALUE
    assert message == "Invalid command line."


def test_classify_bad_option_usage_short_and_fallback() -> None:
    short = click.BadOptionUsage("-p", "missing")
    code, message = classify_usage_error(short)
    assert code is CliErrorCode.MISSING_OPTION_VALUE
    assert message == "Invalid command line."

    bare = click.BadOptionUsage("port", "missing")
    code, message = classify_usage_error(bare)
    assert code is CliErrorCode.MISSING_OPTION_VALUE
    assert message == "Invalid command line."


def test_classify_bad_parameter_without_name() -> None:
    exc = click.BadParameter("bad", param=None)
    code, message = classify_usage_error(exc)
    assert code is CliErrorCode.INVALID_OPTION_VALUE
    assert message == "Invalid command line."


def test_classify_usage_error_unexpected_argument_on_leaf() -> None:
    leaf = click.Command(name="version")
    ctx = click.Context(leaf)
    exc = click.UsageError("extra", ctx=ctx)
    code, message = classify_usage_error(exc)
    assert code is CliErrorCode.UNEXPECTED_ARGUMENT
    assert message == "Unexpected argument."


def test_classify_usage_error_group_stays_command_required() -> None:
    group = click.Group(name="root")
    ctx = click.Context(group)
    exc = click.UsageError("need cmd", ctx=ctx)
    code, message = classify_usage_error(exc)
    assert code is CliErrorCode.COMMAND_REQUIRED
    assert message == "A command is required."


def test_classify_unknown_exception_name_fallback() -> None:
    class OddError(Exception):
        pass

    code, message = classify_usage_error(OddError("x"))  # type: ignore[arg-type]
    assert code is CliErrorCode.COMMAND_REQUIRED
    assert message == "Invalid command line."


def test_catalogued_config_message_timeout_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ConnectionConfig(connect_timeout_s=1)
    assert _catalogued_config_message(exc_info.value) == "Invalid value for --connect-timeout."

    with pytest.raises(ValidationError) as exc_info:
        SessionSafetyConfig(statement_timeout_ms=0)
    assert _catalogued_config_message(exc_info.value) == "Invalid value for --statement-timeout."

    with pytest.raises(ValidationError) as exc_info:
        SessionSafetyConfig(lock_timeout_ms=0)
    assert _catalogued_config_message(exc_info.value) == "Invalid value for --lock-timeout."

    with pytest.raises(ValidationError) as exc_info:
        SessionSafetyConfig(idle_in_transaction_session_timeout_ms=0)
    assert (
        _catalogued_config_message(exc_info.value)
        == "Invalid value for --idle-in-transaction-timeout."
    )


def test_catalogued_config_message_port_and_fallback() -> None:
    port_exc = MagicMock()
    port_exc.errors.return_value = [{"msg": "bad port", "loc": ("port",)}]
    assert _catalogued_config_message(port_exc) == "Invalid value for --port."

    empty = MagicMock()
    empty.errors.return_value = []
    assert _catalogued_config_message(empty) == "Invalid command line."


def test_as_usage_error_vendored_click_module() -> None:
    class FakeNoSuchOption(Exception):
        pass

    FakeNoSuchOption.__module__ = "typer.vendor.click.exceptions"
    FakeNoSuchOption.__name__ = "NoSuchOption"
    assert _as_usage_error(FakeNoSuchOption("x")) is not None

    class Other(Exception):
        pass

    Other.__module__ = "typer.vendor.click.exceptions"
    Other.__name__ = "NotAUsageError"
    assert _as_usage_error(Other("x")) is None

    assert _as_usage_error(RuntimeError("x")) is None
    assert _as_usage_error(click.UsageError("x")) is not None


def test_normalize_command_return_variants() -> None:
    assert normalize_command_return(None) == 0
    assert normalize_command_return(3) == 3
    assert normalize_command_return(SimpleNamespace()) == 0


def test_emit_result_text_debug_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    result = MagicMock()
    result.exit_code = 0
    with (
        patch("pginspect.cli.render_text", return_value="ok\n"),
        patch("pginspect.cli.render_text_debug", return_value="Debug:\n"),
    ):
        assert _emit_result(result, output_format="text", include_debug=True) == 0
    captured = capsys.readouterr()
    assert captured.out == "ok\n"
    assert captured.err == "Debug:\n"


def test_connect_test_invalid_timeout_via_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["connect-test", "--connect-timeout", "1"]) == 4
    err = capsys.readouterr().err
    assert "Invalid value for --connect-timeout." in err


def test_unexpected_exception_in_wrapper_returns_5(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("pginspect.cli.get_command") as get_command:
        command = MagicMock()
        get_command.return_value = command
        command.make_context.side_effect = RuntimeError("unexpected")
        assert main(["version"]) == 5
    assert "pginspect failed due to an internal error." in capsys.readouterr().err


def test_base_exception_reraises() -> None:
    with patch("pginspect.cli.get_command") as get_command:
        command = MagicMock()
        get_command.return_value = command
        command.make_context.side_effect = SystemExit(9)
        with pytest.raises(SystemExit):
            main(["version"])
