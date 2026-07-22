"""Typed configuration models for CLI and connect-test (no password field)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from pginspect.models.base import PublicModel


class SslMode(StrEnum):
    DISABLE = "disable"
    ALLOW = "allow"
    PREFER = "prefer"
    REQUIRE = "require"
    VERIFY_CA = "verify-ca"
    VERIFY_FULL = "verify-full"


class ConnectionConfig(PublicModel):
    """Explicit connection intent. Libpq supplies credentials; never a password here."""

    service: str | None = None
    host: str | None = None
    port: int | None = None
    dbname: str | None = None
    user: str | None = None
    sslmode: SslMode | None = None
    connect_timeout_s: int = Field(default=10, ge=2, le=60)


class SessionSafetyConfig(PublicModel):
    statement_timeout_ms: int = Field(default=15000, ge=1, le=300000)
    lock_timeout_ms: int = Field(default=2000, ge=1, le=60000)
    idle_in_transaction_session_timeout_ms: int = Field(default=15000, ge=1, le=300000)

    @model_validator(mode="after")
    def lock_must_be_less_than_statement(self) -> SessionSafetyConfig:
        if self.lock_timeout_ms >= self.statement_timeout_ms:
            raise ValueError("lock_timeout must be less than statement_timeout.")
        return self


class ConnectTestConfig(PublicModel):
    connection: ConnectionConfig = Field(default_factory=ConnectionConfig)
    session: SessionSafetyConfig = Field(default_factory=SessionSafetyConfig)


class OutputConfig(PublicModel):
    format: Literal["text", "json"] = "text"


class ExecutionOptions(PublicModel):
    include_debug: bool = False
