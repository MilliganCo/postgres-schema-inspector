"""Safe connection factory: build kwargs, connect with autocommit, map errors."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.errors import ConnectionTimeout

from pginspect._version import get_app_version
from pginspect.config import ConnectionConfig
from pginspect.exceptions import (
    ConnectAuthenticationError,
    ConnectDatabaseMissingError,
    ConnectFailedError,
    ConnectNetworkError,
    ConnectTimeoutError,
    ConnectTlsError,
    PginspectConnectError,
    PginspectInternalError,
)
from pginspect.models.enums import ClassificationSource, ExecutionErrorCode
from pginspect.redaction import build_safe_debug_frames


def build_connect_kwargs(config: ConnectionConfig) -> dict[str, str | int]:
    """Build libpq kwargs for psycopg.connect. Never includes password or PG* copies."""
    kwargs: dict[str, str | int] = {
        "connect_timeout": config.connect_timeout_s,
        "fallback_application_name": f"pginspect/{get_app_version()}",
    }
    if config.service is not None:
        kwargs["service"] = config.service
    if config.host is not None:
        kwargs["host"] = config.host
    if config.port is not None:
        kwargs["port"] = config.port
    if config.dbname is not None:
        kwargs["dbname"] = config.dbname
    if config.user is not None:
        kwargs["user"] = config.user
    if config.sslmode is not None:
        kwargs["sslmode"] = config.sslmode.value
    return kwargs


def _driver_type_name(exc: BaseException) -> str:
    return type(exc).__name__


def _map_timeout(exc: ConnectionTimeout) -> ConnectTimeoutError:
    return ConnectTimeoutError(
        code=ExecutionErrorCode.CONNECT_TIMEOUT,
        classification_source=ClassificationSource.CONNECTION_TIMEOUT_TYPE,
        sqlstate=getattr(exc, "sqlstate", None),
        driver_exception_type=_driver_type_name(exc),
        debug_frames=build_safe_debug_frames(exc),
    )


def _audited_tls_signal(exc: psycopg.Error) -> bool:
    """Return True only for a narrow, audited TLS-specific driver signal."""
    # Prefer structured type names over message substring matching.
    name = type(exc).__name__.lower()
    if "ssl" in name or "tls" in name:
        return True
    return False


def _map_psycopg_connect_error(exc: psycopg.Error) -> PginspectConnectError:
    sqlstate = getattr(exc, "sqlstate", None)
    frames = build_safe_debug_frames(exc)
    driver_type = _driver_type_name(exc)
    common: dict[str, Any] = {
        "sqlstate": sqlstate if isinstance(sqlstate, str) else None,
        "driver_exception_type": driver_type,
        "debug_frames": frames,
    }

    if isinstance(sqlstate, str) and sqlstate == "3D000":
        return ConnectDatabaseMissingError(
            code=ExecutionErrorCode.DATABASE_MISSING,
            classification_source=ClassificationSource.SQLSTATE,
            **common,
        )

    if isinstance(sqlstate, str) and sqlstate.startswith("28"):
        return ConnectAuthenticationError(
            code=ExecutionErrorCode.AUTHENTICATION_FAILED,
            classification_source=ClassificationSource.SQLSTATE,
            **common,
        )

    pgconn = getattr(exc, "pgconn", None)
    if pgconn is not None:
        try:
            needs_password = bool(pgconn.needs_password)
        except Exception:  # pragma: no cover - defensive
            needs_password = False
        if needs_password:
            return ConnectAuthenticationError(
                code=ExecutionErrorCode.AUTHENTICATION_FAILED,
                classification_source=ClassificationSource.NEEDS_PASSWORD,
                **common,
            )

    if isinstance(sqlstate, str) and sqlstate.startswith("08"):
        return ConnectNetworkError(
            code=ExecutionErrorCode.NETWORK_UNREACHABLE,
            classification_source=ClassificationSource.SQLSTATE,
            **common,
        )

    if _audited_tls_signal(exc):
        return ConnectTlsError(
            code=ExecutionErrorCode.TLS_FAILED,
            classification_source=ClassificationSource.AUDITED_TLS_SIGNAL,
            **common,
        )

    return ConnectFailedError(
        code=ExecutionErrorCode.CONNECTION_FAILED,
        classification_source=ClassificationSource.FALLBACK_OTHER,
        **common,
    )


def _map_internal_connect_error(exc: BaseException) -> PginspectInternalError:
    return PginspectInternalError(
        "unexpected error during connect",
        debug_frames=build_safe_debug_frames(exc),
        driver_exception_type=_driver_type_name(exc),
    )


def _connect(config: ConnectionConfig) -> Connection[Any]:
    kwargs = build_connect_kwargs(config)
    mapped: PginspectConnectError | PginspectInternalError | None = None
    try:
        return psycopg.connect(autocommit=True, **kwargs)
    except ConnectionTimeout as exc:
        mapped = _map_timeout(exc)
    except psycopg.Error as exc:
        mapped = _map_psycopg_connect_error(exc)
    except Exception as exc:
        mapped = _map_internal_connect_error(exc)
    # Raise outside the active except block so __cause__/__context__ stay clear.
    assert mapped is not None
    raise mapped


@contextmanager
def open_connection(config: ConnectionConfig) -> Iterator[Connection[Any]]:
    """Open a connection with autocommit=True; always close on exit."""
    conn = _connect(config)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            # Cleanup must not mask an active primary exception.
            pass
