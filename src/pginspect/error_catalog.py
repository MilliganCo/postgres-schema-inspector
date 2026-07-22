"""Catalogued public messages and retryability for execution errors."""

from __future__ import annotations

from pginspect.models.enums import ExecutionErrorCode

_PUBLIC_CONNECT_MESSAGES: dict[ExecutionErrorCode, str] = {
    ExecutionErrorCode.AUTHENTICATION_FAILED: "PostgreSQL authentication failed.",
    ExecutionErrorCode.NETWORK_UNREACHABLE: (
        "Could not establish a network connection to PostgreSQL."
    ),
    ExecutionErrorCode.CONNECT_TIMEOUT: "Connection attempt timed out.",
    ExecutionErrorCode.TLS_FAILED: "TLS negotiation with PostgreSQL failed.",
    ExecutionErrorCode.DATABASE_MISSING: "The specified database does not exist.",
    ExecutionErrorCode.CONNECTION_FAILED: "Could not connect to PostgreSQL.",
    ExecutionErrorCode.OPERATIONAL_FAILURE: (
        "The PostgreSQL session failed during a diagnostic operation."
    ),
    ExecutionErrorCode.INTERNAL_FAILURE: "pginspect failed due to an internal error.",
}

_RETRYABLE: dict[ExecutionErrorCode, bool] = {
    ExecutionErrorCode.AUTHENTICATION_FAILED: False,
    ExecutionErrorCode.NETWORK_UNREACHABLE: True,
    ExecutionErrorCode.CONNECT_TIMEOUT: True,
    ExecutionErrorCode.TLS_FAILED: False,
    ExecutionErrorCode.DATABASE_MISSING: False,
    ExecutionErrorCode.CONNECTION_FAILED: False,
    ExecutionErrorCode.OPERATIONAL_FAILURE: True,
    ExecutionErrorCode.INTERNAL_FAILURE: False,
}


def public_connect_message(code: ExecutionErrorCode) -> str:
    """Return the catalogued English public message for an execution error code."""
    try:
        return _PUBLIC_CONNECT_MESSAGES[code]
    except KeyError as exc:  # pragma: no cover - closed enum
        raise ValueError(f"unknown execution error code: {code!r}") from exc


def retryable_for(code: ExecutionErrorCode) -> bool:
    """Return whether the error code is considered retryable."""
    try:
        return _RETRYABLE[code]
    except KeyError as exc:  # pragma: no cover - closed enum
        raise ValueError(f"unknown execution error code: {code!r}") from exc
