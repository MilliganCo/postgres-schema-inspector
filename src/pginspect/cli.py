"""pginspect CLI: Typer commands and ``main()`` process wrapper."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Optional

import click
import typer
from pydantic import ValidationError
from typer.core import TyperGroup
from typer.main import get_command

from pginspect.config import (
    ConnectionConfig,
    ConnectTestConfig,
    ExecutionOptions,
    OutputConfig,
    SessionSafetyConfig,
    SslMode,
)
from pginspect.connectivity import build_version_result, run_connect_test
from pginspect.exceptions import PginspectConfigurationError
from pginspect.renderers import render_json, render_text, render_text_debug

_FATAL_MESSAGE = "pginspect failed due to an internal error."


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"


class CliErrorCode(StrEnum):
    INVALID_OPTION_VALUE = "invalid_option_value"
    MISSING_OPTION_VALUE = "missing_option_value"
    UNKNOWN_OPTION = "unknown_option"
    UNKNOWN_COMMAND = "unknown_command"
    UNEXPECTED_ARGUMENT = "unexpected_argument"
    COMMAND_REQUIRED = "command_required"
    CONFIGURATION_INVALID = "configuration_invalid"


class CommandRequiredError(click.UsageError):
    """Raised when argv contains no command."""


class UnknownCommandError(click.UsageError):
    """Raised when the first token is not a known command (token never echoed)."""


class PginspectGroup(TyperGroup):
    """Typer group that raises typed usage errors without echoing argv tokens."""

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        if not args:
            raise CommandRequiredError("A command is required.", ctx)
        first = args[0]
        if not first.startswith("-") and self.get_command(ctx, first) is None:
            raise UnknownCommandError("Unknown command.", ctx)
        return super().resolve_command(ctx, args)


app = typer.Typer(
    cls=PginspectGroup,
    add_completion=False,
    no_args_is_help=False,
    invoke_without_command=False,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
    rich_markup_mode=None,
    context_settings={
        "help_option_names": ["--help"],
    },
)

OutputFormatOption = Annotated[
    OutputFormat,
    typer.Option(
        "--format",
        help="Output format.",
        case_sensitive=False,
    ),
]


def _long_option_name(param: click.Parameter | None) -> str | None:
    if param is None:
        return None
    opts = tuple(getattr(param, "opts", ()) or ())
    for opt in opts:
        if isinstance(opt, str) and opt.startswith("--"):
            return opt[2:]
    name = getattr(param, "name", None)
    return str(name) if name else None


def classify_usage_error(exc: click.UsageError) -> tuple[CliErrorCode, str]:
    """Map Click usage exceptions to catalogued messages (never echo values)."""
    name = type(exc).__name__
    if isinstance(exc, CommandRequiredError) or name == "CommandRequiredError":
        return CliErrorCode.COMMAND_REQUIRED, "A command is required."
    if isinstance(exc, UnknownCommandError) or name == "UnknownCommandError":
        return CliErrorCode.UNKNOWN_COMMAND, "Unknown command."
    if isinstance(exc, click.NoSuchOption) or name == "NoSuchOption":
        return CliErrorCode.UNKNOWN_OPTION, "Unknown option."
    if isinstance(exc, click.MissingParameter) or name == "MissingParameter":
        param_name = _long_option_name(getattr(exc, "param", None))
        if param_name:
            return CliErrorCode.MISSING_OPTION_VALUE, f"Missing value for --{param_name}."
        return CliErrorCode.MISSING_OPTION_VALUE, "Invalid command line."
    if isinstance(exc, click.BadOptionUsage) or name == "BadOptionUsage":
        option = getattr(exc, "option_name", None)
        if isinstance(option, str) and option.startswith("--"):
            opt_name = option[2:]
            return CliErrorCode.MISSING_OPTION_VALUE, f"Missing value for --{opt_name}."
        if isinstance(option, str) and option.startswith("-") and len(option) == 2:
            return CliErrorCode.MISSING_OPTION_VALUE, "Invalid command line."
        return CliErrorCode.MISSING_OPTION_VALUE, "Invalid command line."
    if isinstance(exc, click.BadParameter) or name == "BadParameter":
        param_name = _long_option_name(getattr(exc, "param", None))
        if param_name:
            return CliErrorCode.INVALID_OPTION_VALUE, f"Invalid value for --{param_name}."
        return CliErrorCode.INVALID_OPTION_VALUE, "Invalid command line."
    if isinstance(exc, click.UsageError) or name == "UsageError":
        ctx = getattr(exc, "ctx", None)
        command = getattr(ctx, "command", None) if ctx is not None else None
        if command is not None and not isinstance(command, click.Group):
            # Typer may vendor Group; treat non-group leaf commands as unexpected args.
            cmd_type = type(command).__name__
            if cmd_type not in {"Group", "TyperGroup", "PginspectGroup"} and not isinstance(
                command, click.Group
            ):
                return CliErrorCode.UNEXPECTED_ARGUMENT, "Unexpected argument."
        return CliErrorCode.COMMAND_REQUIRED, "A command is required."
    return CliErrorCode.COMMAND_REQUIRED, "Invalid command line."


def _emit_result(result: object, *, output_format: str, include_debug: bool) -> int:
    exit_code = int(getattr(result, "exit_code"))
    try:
        if output_format == "json":
            click.echo(render_json(result), nl=False)  # type: ignore[arg-type]
        else:
            click.echo(render_text(result), nl=False)  # type: ignore[arg-type]
            if include_debug:
                debug = render_text_debug(result)  # type: ignore[arg-type]
                if debug:
                    click.echo(debug, nl=False, err=True)
    except Exception:
        click.echo(_FATAL_MESSAGE, err=True)
        return 5
    return exit_code


def normalize_command_return(result: object) -> int:
    if result is None:
        return 0
    if isinstance(result, int):
        return int(result)
    return 0


@app.command("version")
def version_command(
    format: OutputFormatOption = OutputFormat.TEXT,
) -> int:
    """Print the installed pginspect version."""
    result = build_version_result()
    return _emit_result(result, output_format=format.value, include_debug=False)


@app.command("connect-test")
def connect_test_command(
    service: Annotated[Optional[str], typer.Option("--service", help="Libpq service name.")] = None,
    host: Annotated[
        Optional[str],
        typer.Option("-h", "--host", help="PostgreSQL host."),
    ] = None,
    port: Annotated[
        Optional[int],
        typer.Option("-p", "--port", help="PostgreSQL port."),
    ] = None,
    dbname: Annotated[
        Optional[str],
        typer.Option("-d", "--dbname", help="Database name."),
    ] = None,
    user: Annotated[
        Optional[str],
        typer.Option("-U", "--user", help="Database user."),
    ] = None,
    sslmode: Annotated[
        Optional[SslMode],
        typer.Option("--sslmode", help="Libpq sslmode.", case_sensitive=False),
    ] = None,
    connect_timeout: Annotated[
        int,
        typer.Option(
            "--connect-timeout",
            help="Connect timeout in seconds (2-60).",
        ),
    ] = 10,
    statement_timeout: Annotated[
        int,
        typer.Option("--statement-timeout", help="statement_timeout in milliseconds."),
    ] = 15000,
    lock_timeout: Annotated[
        int,
        typer.Option("--lock-timeout", help="lock_timeout in milliseconds."),
    ] = 2000,
    idle_in_transaction_timeout: Annotated[
        int,
        typer.Option(
            "--idle-in-transaction-timeout",
            help="idle_in_transaction_session_timeout in milliseconds.",
        ),
    ] = 15000,
    format: OutputFormatOption = OutputFormat.TEXT,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Include structured debug payload when present."),
    ] = False,
) -> int:
    """Establish a read-only diagnostic session and report connection health."""
    _ = OutputConfig(format=format.value)
    execution = ExecutionOptions(include_debug=debug)
    try:
        connection = ConnectionConfig(
            service=service,
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            sslmode=sslmode,
            connect_timeout_s=connect_timeout,
        )
        session = SessionSafetyConfig(
            statement_timeout_ms=statement_timeout,
            lock_timeout_ms=lock_timeout,
            idle_in_transaction_session_timeout_ms=idle_in_transaction_timeout,
        )
        config = ConnectTestConfig(connection=connection, session=session)
    except ValidationError as exc:
        message = _catalogued_config_message(exc)
        raise PginspectConfigurationError(message) from None

    result = run_connect_test(config, include_debug=execution.include_debug)
    return _emit_result(
        result,
        output_format=format.value,
        include_debug=execution.include_debug,
    )


def _catalogued_config_message(exc: ValidationError) -> str:
    """Map Pydantic validation failures to catalogued English messages (no repr)."""
    for err in exc.errors():
        msg = err.get("msg", "")
        if "lock_timeout must be less than statement_timeout" in msg:
            return "lock_timeout must be less than statement_timeout."
        loc = err.get("loc", ())
        if "connect_timeout_s" in loc or "connect_timeout" in loc:
            return "Invalid value for --connect-timeout."
        if "statement_timeout_ms" in loc:
            return "Invalid value for --statement-timeout."
        if "lock_timeout_ms" in loc:
            return "Invalid value for --lock-timeout."
        if "idle_in_transaction_session_timeout_ms" in loc:
            return "Invalid value for --idle-in-transaction-timeout."
        if "port" in loc:
            return "Invalid value for --port."
    return "Invalid command line."


def _is_exit_exception(exc: BaseException) -> bool:
    """Click/Typer deliberate exit (``--help``); Typer>=0.17 vendors its own Exit type."""
    return type(exc).__name__ == "Exit" and hasattr(exc, "exit_code")


def _as_usage_error(exc: BaseException) -> click.UsageError | None:
    """Return a Click-compatible usage error, including Typer-vendored exception types."""
    if isinstance(exc, click.UsageError):
        return exc
    module = type(exc).__module__
    if "click" not in module or not module.endswith(".exceptions"):
        return None
    name = type(exc).__name__
    if name in {
        "UsageError",
        "BadParameter",
        "NoSuchOption",
        "MissingParameter",
        "BadOptionUsage",
        "BadArgumentUsage",
    }:
        # Our classifiers only need type()/param/option_name attributes.
        return exc  # type: ignore[return-value]
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Process wrapper: map usage→4, interrupt→130, fatal→5; else command exit int."""
    args = list(sys.argv[1:] if argv is None else argv)
    command = get_command(app)

    try:
        with command.make_context("pginspect", args) as context:
            result = command.invoke(context)
    except BaseException as exc:
        if _is_exit_exception(exc):
            return int(getattr(exc, "exit_code"))
        usage = _as_usage_error(exc)
        if usage is not None:
            _code, message = classify_usage_error(usage)
            _ = _code
            click.echo(message, err=True)
            return 4
        if isinstance(exc, PginspectConfigurationError):
            click.echo(exc.public_message, err=True)
            return 4
        if isinstance(exc, KeyboardInterrupt):
            return 130
        if isinstance(exc, Exception):
            click.echo(_FATAL_MESSAGE, err=True)
            return 5
        raise

    return normalize_command_return(result)
