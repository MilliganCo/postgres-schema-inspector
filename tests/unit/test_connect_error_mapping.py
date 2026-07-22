"""Tests for connect error classification and domain exception hygiene."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import psycopg
import pytest
from psycopg.errors import (
    ConnectionFailure,
    ConnectionTimeout,
    InternalError_,
    InvalidCatalogName,
    InvalidPassword,
)

from pginspect.config import ConnectionConfig
from pginspect.connection import _connect, open_connection
from pginspect.exceptions import (
    ConnectAuthenticationError,
    ConnectDatabaseMissingError,
    ConnectFailedError,
    ConnectNetworkError,
    ConnectTimeoutError,
    PginspectInternalError,
)
from pginspect.models.enums import ClassificationSource, ExecutionErrorCode


def test_connection_timeout_maps_to_connect_timeout_error() -> None:
    with patch("pginspect.connection.psycopg.connect", side_effect=ConnectionTimeout("timeout")):
        with pytest.raises(ConnectTimeoutError) as exc_info:
            _connect(ConnectionConfig())
    err = exc_info.value
    assert err.code is ExecutionErrorCode.CONNECT_TIMEOUT
    assert err.classification_source is ClassificationSource.CONNECTION_TIMEOUT_TYPE
    assert err.__cause__ is None
    assert err.__context__ is None


def test_28p01_maps_to_authentication() -> None:
    with patch(
        "pginspect.connection.psycopg.connect",
        side_effect=InvalidPassword("bad password"),
    ):
        with pytest.raises(ConnectAuthenticationError) as exc_info:
            _connect(ConnectionConfig())
    assert exc_info.value.code is ExecutionErrorCode.AUTHENTICATION_FAILED
    assert exc_info.value.classification_source is ClassificationSource.SQLSTATE
    assert exc_info.value.sqlstate == "28P01"


def test_3d000_maps_to_database_missing() -> None:
    with patch(
        "pginspect.connection.psycopg.connect",
        side_effect=InvalidCatalogName("missing"),
    ):
        with pytest.raises(ConnectDatabaseMissingError) as exc_info:
            _connect(ConnectionConfig())
    assert exc_info.value.code is ExecutionErrorCode.DATABASE_MISSING
    assert exc_info.value.sqlstate == "3D000"


def test_08xxx_maps_to_network() -> None:
    with patch(
        "pginspect.connection.psycopg.connect",
        side_effect=ConnectionFailure("gone"),
    ):
        with pytest.raises(ConnectNetworkError) as exc_info:
            _connect(ConnectionConfig())
    assert exc_info.value.code is ExecutionErrorCode.NETWORK_UNREACHABLE
    assert exc_info.value.classification_source is ClassificationSource.SQLSTATE


def test_needs_password_maps_to_authentication() -> None:
    pgconn = MagicMock()
    pgconn.needs_password = True
    exc = ConnectionFailure("need password")
    # Force a non-08 path: clear sqlstate classification by using InternalError_ base.
    # ConnectionFailure is 08*; use a generic Error without 08/28/3D000 sqlstate.
    exc = InternalError_("need password")
    exc._pgconn = pgconn  # type: ignore[attr-defined]
    with patch("pginspect.connection.psycopg.connect", side_effect=exc):
        with pytest.raises(ConnectAuthenticationError) as exc_info:
            _connect(ConnectionConfig())
    assert exc_info.value.classification_source is ClassificationSource.NEEDS_PASSWORD
    assert "pgconn" not in exc_info.value.__dict__


def test_unknown_psycopg_error_maps_to_other() -> None:
    with patch(
        "pginspect.connection.psycopg.connect",
        side_effect=InternalError_("weird"),
    ):
        with pytest.raises(ConnectFailedError) as exc_info:
            _connect(ConnectionConfig())
    assert exc_info.value.code is ExecutionErrorCode.CONNECTION_FAILED
    assert exc_info.value.classification_source is ClassificationSource.FALLBACK_OTHER


def test_non_psycopg_exception_maps_to_internal() -> None:
    with patch(
        "pginspect.connection.psycopg.connect",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(PginspectInternalError) as exc_info:
            _connect(ConnectionConfig())
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_open_connection_closes_on_success() -> None:
    mock_conn = MagicMock()
    mock_conn.closed = False
    with patch("pginspect.connection.psycopg.connect", return_value=mock_conn):
        with open_connection(ConnectionConfig()) as conn:
            assert conn is mock_conn
    mock_conn.close.assert_called_once()


def test_open_connection_closes_after_session_error() -> None:
    mock_conn = MagicMock()
    with patch("pginspect.connection.psycopg.connect", return_value=mock_conn):
        with pytest.raises(RuntimeError, match="session boom"):
            with open_connection(ConnectionConfig()):
                raise RuntimeError("session boom")
    mock_conn.close.assert_called_once()


def test_domain_exception_retains_no_raw_exception_object() -> None:
    raw = InvalidPassword("bad password")
    with patch("pginspect.connection.psycopg.connect", side_effect=raw):
        with pytest.raises(ConnectAuthenticationError) as exc_info:
            _connect(ConnectionConfig())
    err = exc_info.value
    assert err.__cause__ is None
    assert err.__context__ is None
    assert "pgconn" not in err.__dict__
    assert not any(isinstance(v, psycopg.Error) for v in err.__dict__.values())
