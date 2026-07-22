"""Tests for error catalog messages and retryability."""

from __future__ import annotations

import pytest

from pginspect.error_catalog import public_connect_message, retryable_for
from pginspect.models.enums import ExecutionErrorCode
from pginspect.redaction import sanitize_untrusted_text

CANARY_PASSWORD = "CANARY_PASSWORD_7f03"
CANARY_HOST = "secret-db.internal.example"
CANARY_DSN = f"postgresql://private_role:{CANARY_PASSWORD}@{CANARY_HOST}:5432/db"
CANARY_PATH = "/home/alice/.pgpass"


@pytest.mark.parametrize("code", list(ExecutionErrorCode))
def test_public_connect_message_is_catalogued_and_canary_free(code: ExecutionErrorCode) -> None:
    message = public_connect_message(code)
    assert isinstance(message, str)
    assert message
    assert CANARY_PASSWORD not in message
    assert CANARY_HOST not in message
    assert CANARY_DSN not in message
    assert CANARY_PATH not in message
    # Catalog messages must already be safe; sanitizer must be a no-op.
    assert sanitize_untrusted_text(message) == message


def test_known_connect_messages() -> None:
    assert (
        public_connect_message(ExecutionErrorCode.AUTHENTICATION_FAILED)
        == "PostgreSQL authentication failed."
    )
    assert public_connect_message(ExecutionErrorCode.CONNECT_TIMEOUT) == (
        "Connection attempt timed out."
    )
    assert public_connect_message(ExecutionErrorCode.INTERNAL_FAILURE) == (
        "pginspect failed due to an internal error."
    )


def test_retryable_for_table() -> None:
    assert retryable_for(ExecutionErrorCode.NETWORK_UNREACHABLE) is True
    assert retryable_for(ExecutionErrorCode.CONNECT_TIMEOUT) is True
    assert retryable_for(ExecutionErrorCode.OPERATIONAL_FAILURE) is True
    assert retryable_for(ExecutionErrorCode.AUTHENTICATION_FAILED) is False
    assert retryable_for(ExecutionErrorCode.DATABASE_MISSING) is False
    assert retryable_for(ExecutionErrorCode.TLS_FAILED) is False
    assert retryable_for(ExecutionErrorCode.CONNECTION_FAILED) is False
    assert retryable_for(ExecutionErrorCode.INTERNAL_FAILURE) is False


def test_retryable_covers_all_codes() -> None:
    for code in ExecutionErrorCode:
        assert isinstance(retryable_for(code), bool)
