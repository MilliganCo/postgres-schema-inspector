"""Shared PostgreSQL fixtures for integration tests.

Skips the entire module collection path when ``PGINSPECT_TEST_DSN`` is unset so
default ``pytest`` (``tests/unit`` only) and local runs without Postgres stay green.
When set (CI service or local Docker), applies ``tests/fixtures/pginspect_probe.sql``.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import pytest

from pginspect.config import ConnectionConfig, ConnectTestConfig, SessionSafetyConfig

FIXTURE_SQL = Path(__file__).resolve().parents[1] / "fixtures" / "pginspect_probe.sql"

SUBJECT_USER = "pginspect_test"
SUBJECT_PASSWORD = "pginspect_test_ci"
ADMIN_USER = "pginspect_admin"
ADMIN_PASSWORD = "pginspect_admin_ci"

_DSN = os.environ.get("PGINSPECT_TEST_DSN", "").strip()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: tests requiring PostgreSQL")


def _require_dsn() -> str:
    if not _DSN:
        pytest.skip(
            "PGINSPECT_TEST_DSN unset; integration tests require a live PostgreSQL "
            "(set by GHA services or local Docker)."
        )
    return _DSN


def _parse_dsn(dsn: str) -> dict[str, str | int]:
    """Extract host/port/dbname from a URI or keyword DSN for ConnectionConfig."""
    if "://" in dsn:
        parsed = urlparse(dsn)
        out: dict[str, str | int] = {}
        if parsed.hostname:
            out["host"] = parsed.hostname
        if parsed.port:
            out["port"] = int(parsed.port)
        db = parsed.path.lstrip("/") if parsed.path else ""
        if db:
            out["dbname"] = db
        return out
    # keyword/value form: host=... port=... dbname=...
    out = {}
    for part in dsn.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key in {"host", "dbname"}:
            out[key] = value
        elif key == "port":
            out[key] = int(value)
    return out


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    return _require_dsn()


@pytest.fixture(scope="session")
def _apply_probe_fixture(pg_dsn: str) -> None:
    sql = FIXTURE_SQL.read_text(encoding="utf-8")
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute(sql)
        row = conn.execute("SHOW server_version_num").fetchone()
        assert row is not None
        version_num = int(row[0])
        expected_major = os.environ.get("PGINSPECT_EXPECT_PG_MAJOR", "").strip()
        if expected_major:
            major = version_num // 10000
            assert major == int(expected_major), (
                f"server_version_num={version_num} major={major} "
                f"!= expected {expected_major}"
            )


@pytest.fixture(scope="session")
def pg_endpoint(pg_dsn: str, _apply_probe_fixture: None) -> dict[str, str | int]:
    return _parse_dsn(pg_dsn)


@pytest.fixture
def subject_password_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Libpq auth for subject role (app never copies PGPASSWORD into kwargs)."""
    monkeypatch.setenv("PGPASSWORD", SUBJECT_PASSWORD)


@pytest.fixture
def admin_password_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGPASSWORD", ADMIN_PASSWORD)


@pytest.fixture
def subject_connection_config(
    pg_endpoint: dict[str, str | int],
    subject_password_env: None,
) -> ConnectionConfig:
    return ConnectionConfig(
        host=str(pg_endpoint.get("host", "127.0.0.1")),
        port=int(pg_endpoint.get("port", 5432)),
        dbname=str(pg_endpoint.get("dbname", "postgres")),
        user=SUBJECT_USER,
        connect_timeout_s=10,
    )


@pytest.fixture
def admin_connection_config(
    pg_endpoint: dict[str, str | int],
    admin_password_env: None,
) -> ConnectionConfig:
    return ConnectionConfig(
        host=str(pg_endpoint.get("host", "127.0.0.1")),
        port=int(pg_endpoint.get("port", 5432)),
        dbname=str(pg_endpoint.get("dbname", "postgres")),
        user=ADMIN_USER,
        connect_timeout_s=10,
    )


@pytest.fixture
def connect_test_config(subject_connection_config: ConnectionConfig) -> ConnectTestConfig:
    return ConnectTestConfig(
        connection=subject_connection_config,
        session=SessionSafetyConfig(),
    )


@pytest.fixture
def closed_local_port() -> int:
    """Bind then close so connect attempts get connection refused (F-09)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    time.sleep(0.05)
    return port


@pytest.fixture
def stall_server() -> Iterator[int]:
    """Loopback TCP server that accepts but never completes the protocol (F-10)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    port = int(sock.getsockname()[1])
    stop = threading.Event()
    held: list[socket.socket] = []

    def _serve() -> None:
        sock.settimeout(0.5)
        while not stop.is_set():
            try:
                conn, _addr = sock.accept()
                held.append(conn)
            except TimeoutError:
                continue
            except OSError:
                break

    thread = threading.Thread(target=_serve, name="pginspect-stall", daemon=True)
    thread.start()
    try:
        yield port
    finally:
        stop.set()
        thread.join(timeout=2)
        for conn in held:
            try:
                conn.close()
            except OSError:
                pass
        try:
            sock.close()
        except OSError:
            pass


def observer_sentinel(pg_endpoint: dict[str, str | int], password: str = ADMIN_PASSWORD) -> str:
    """Return payload of sentinel row via observer role."""
    conninfo = (
        f"host={pg_endpoint.get('host', '127.0.0.1')} "
        f"port={pg_endpoint.get('port', 5432)} "
        f"dbname={pg_endpoint.get('dbname', 'postgres')} "
        f"user={ADMIN_USER} password={password}"
    )
    with psycopg.connect(conninfo) as conn:
        row = conn.execute(
            "SELECT payload FROM pginspect_probe.write_probe WHERE id = 1"
        ).fetchone()
        assert row is not None
        return str(row[0])
