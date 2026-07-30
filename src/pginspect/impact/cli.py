"""Thin impact CLI command (plan Task 11).

Typer receives a `Path` and forwards it to `run_impact`. This module never
opens, stats, or reads the migration path — only `impact.input` may do I/O.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Optional

import click
import typer
from pydantic import ValidationError

from pginspect.config import ConnectionConfig, OutputConfig, SessionSafetyConfig, SslMode
from pginspect.exceptions import PginspectConfigurationError
from pginspect.impact.input import LocalPhaseError
from pginspect.impact.renderers import (
    render_impact_json,
    render_impact_text,
    render_impact_text_debug,
)
from pginspect.impact.run import run_impact

_FATAL_MESSAGE = "pginspect failed due to an internal error."
_OutputFormat = Literal["text", "json"]


def _emit_impact_result(result: object, *, output_format: str, include_debug: bool) -> int:
    exit_code = int(getattr(result, "exit_code"))
    try:
        if output_format == "json":
            click.echo(render_impact_json(result), nl=False)  # type: ignore[arg-type]
        else:
            click.echo(render_impact_text(result), nl=False)  # type: ignore[arg-type]
            if include_debug:
                debug = render_impact_text_debug(result)  # type: ignore[arg-type]
                if debug:
                    click.echo(debug, nl=False, err=True)
    except Exception:
        click.echo(_FATAL_MESSAGE, err=True)
        return 5
    return exit_code


def register_impact_command(app: typer.Typer) -> None:
    """Register the `impact` subcommand on the root Typer app."""

    @app.command("impact")
    def impact_command(
        migration: Annotated[
            Path,
            typer.Argument(help="Migration SQL file path (opened only inside impact.input)."),
        ],
        service: Annotated[
            Optional[str], typer.Option("--service", help="Libpq service name.")
        ] = None,
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
            typer.Option("--connect-timeout", help="Connect timeout in seconds (2-60)."),
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
        format: Annotated[
            str,
            typer.Option("--format", help="Output format.", case_sensitive=False),
        ] = "text",
        debug: Annotated[
            bool,
            typer.Option("--debug", help="Include structured debug payload when present."),
        ] = False,
    ) -> int:
        """Analyze change impact of a migration script against a live catalog."""
        fmt = format.lower()
        if fmt == "json":
            output_format: _OutputFormat = "json"
        elif fmt == "text":
            output_format = "text"
        else:
            raise PginspectConfigurationError("Invalid value for --format.")
        _ = OutputConfig(format=output_format)
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
        except ValidationError as exc:
            raise PginspectConfigurationError(_config_message(exc)) from None

        try:
            result = run_impact(migration, connection, session)
        except LocalPhaseError as exc:
            click.echo(exc.public_message, err=True)
            return 4

        return _emit_impact_result(result, output_format=output_format, include_debug=debug)


def _config_message(exc: ValidationError) -> str:
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
