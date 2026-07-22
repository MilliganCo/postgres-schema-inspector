"""Tests for ConnectionConfig / SessionSafetyConfig and related models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pginspect.config import (
    ConnectionConfig,
    ConnectTestConfig,
    ExecutionOptions,
    OutputConfig,
    SessionSafetyConfig,
    SslMode,
)


def test_lock_timeout_must_be_less_than_statement_timeout() -> None:
    with pytest.raises(ValidationError):
        SessionSafetyConfig(statement_timeout_ms=1000, lock_timeout_ms=1000)


def test_lock_timeout_equal_statement_rejected() -> None:
    with pytest.raises(ValidationError, match="lock_timeout"):
        SessionSafetyConfig(statement_timeout_ms=2000, lock_timeout_ms=2000)


def test_defaults() -> None:
    conn = ConnectionConfig()
    session = SessionSafetyConfig()
    assert conn.connect_timeout_s == 10
    assert session.statement_timeout_ms == 15000
    assert session.lock_timeout_ms == 2000
    assert session.idle_in_transaction_session_timeout_ms == 15000


def test_connection_config_has_no_password_field() -> None:
    assert "password" not in ConnectionConfig.model_fields
    with pytest.raises(ValidationError):
        ConnectionConfig.model_validate({"password": "secret"})  # type: ignore[arg-type]


def test_connect_timeout_bounds() -> None:
    with pytest.raises(ValidationError):
        ConnectionConfig(connect_timeout_s=0)
    with pytest.raises(ValidationError):
        ConnectionConfig(connect_timeout_s=1)
    with pytest.raises(ValidationError):
        ConnectionConfig(connect_timeout_s=61)
    assert ConnectionConfig(connect_timeout_s=2).connect_timeout_s == 2
    assert ConnectionConfig(connect_timeout_s=60).connect_timeout_s == 60


def test_sslmode_values() -> None:
    assert ConnectionConfig(sslmode=SslMode.VERIFY_FULL).sslmode is SslMode.VERIFY_FULL
    assert SslMode.REQUIRE.value == "require"


def test_connect_test_and_output_defaults() -> None:
    cfg = ConnectTestConfig()
    assert cfg.connection.connect_timeout_s == 10
    assert cfg.session.lock_timeout_ms == 2000
    assert OutputConfig().format == "text"
    assert ExecutionOptions().include_debug is False
