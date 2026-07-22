"""Tests for build_connect_kwargs safety and required parameters."""

from __future__ import annotations

from pginspect.config import ConnectionConfig
from pginspect.connection import build_connect_kwargs


def test_build_connect_kwargs_never_includes_password(monkeypatch: object) -> None:
    monkeypatch.setenv("PGPASSWORD", "CANARY_PASSWORD_7f03")  # type: ignore[attr-defined]
    kwargs = build_connect_kwargs(ConnectionConfig(connect_timeout_s=10))
    assert "password" not in kwargs
    assert "PGPASSWORD" not in kwargs
    assert "CANARY_PASSWORD_7f03" not in repr(kwargs)


def test_build_connect_kwargs_sets_timeout_and_fallback_app_name() -> None:
    kwargs = build_connect_kwargs(ConnectionConfig())
    assert kwargs["connect_timeout"] == 10
    assert isinstance(kwargs["fallback_application_name"], str)
    assert kwargs["fallback_application_name"].startswith("pginspect/")


def test_does_not_copy_pghost_into_kwargs(monkeypatch: object) -> None:
    monkeypatch.setenv("PGHOST", "secret-db.internal.example")  # type: ignore[attr-defined]
    kwargs = build_connect_kwargs(ConnectionConfig())
    assert "host" not in kwargs
    assert "secret-db.internal.example" not in repr(kwargs)


def test_explicit_fields_included_when_set() -> None:
    from pginspect.config import SslMode

    kwargs = build_connect_kwargs(
        ConnectionConfig(
            service="myservice",
            host="db.example",
            port=5433,
            dbname="shop",
            user="monitor",
            sslmode=SslMode.REQUIRE,
            connect_timeout_s=12,
        )
    )
    assert kwargs["service"] == "myservice"
    assert kwargs["host"] == "db.example"
    assert kwargs["port"] == 5433
    assert kwargs["dbname"] == "shop"
    assert kwargs["user"] == "monitor"
    assert kwargs["sslmode"] == "require"
    assert kwargs["connect_timeout"] == 12
    assert "password" not in kwargs
