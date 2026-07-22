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
    if isinstance(exc, CommandRequiredError):
        return CliErrorCode.COMMAND_REQUIRED, "A command is required."
    if isinstance(exc, UnknownCommandError):
        return CliErrorCode.UNKNOWN_COMMAND, "Unknown command."
    if isinstance(exc, click.NoSuchOption):
        return CliErrorCode.UNKNOWN_OPTION, "Unknown option."
    if isinstance(exc, click.MissingParameter):
        name = _long_option_name(exc.param)
        if name:
            return CliErrorCode.MISSING_OPTION_VALUE, f"Missing value for --{name}."
        return CliErrorCode.MISSING_OPTION_VALUE, "Invalid command line."
    if isinstance(exc, click.BadOptionUsage):
        option = getattr(exc, "option_name", None)
        if isinstance(option, str) and option.startswith("--"):
            name = option[2:]
            return CliErrorCode.MISSING_OPTION_VALUE, f"Missing value for --{name}."
        if isinstance(option, str) and option.startswith("-") and len(option) == 2:
            # Map short option to catalogued long name when possible via ctx — keep generic.
            return CliErrorCode.MISSING_OPTION_VALUE, "Invalid command line."
        return CliErrorCode.MISSING_OPTION_VALUE, "Invalid command line."
    if isinstance(exc, click.BadParameter):
        name = _long_option_name(exc.param)
        if name:
            return CliErrorCode.INVALID_OPTION_VALUE, f"Invalid value for --{name}."
        return CliErrorCode.INVALID_OPTION_VALUE, "Invalid command line."
    if isinstance(exc, click.UsageError):
        ctx = exc.ctx
        if ctx is not None and not isinstance(ctx.command, click.Group):
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


def main(argv: Sequence[str] | None = None) -> int:
    """Process wrapper: map usage→4, interrupt→130, fatal→5; else command exit int."""
    args = list(sys.argv[1:] if argv is None else argv)
    command = get_command(app)

    try:
        with command.make_context("pginspect", args) as context:
            result = command.invoke(context)
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    except click.UsageError as exc:
        _code, message = classify_usage_error(exc)
        _ = _code
        click.echo(message, err=True)
        return 4
    except PginspectConfigurationError as exc:
        click.echo(exc.public_message, err=True)
        return 4
    except KeyboardInterrupt:
        return 130
    except Exception:
        click.echo(_FATAL_MESSAGE, err=True)
        return 5

    return normalize_command_return(result)
