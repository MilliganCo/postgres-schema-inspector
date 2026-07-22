"""Safety suite fixtures — skip cleanly when ``PGINSPECT_TEST_DSN`` is unset."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from pginspect.config import ConnectionConfig

from tests.safety._helpers import (
    SUBJECT_PASSWORD,
    SUBJECT_USER,
    assert_subject_has_write_grants,
    parse_dsn,
)

FIXTURE_SQL = Path(__file__).resolve().parents[1] / "fixtures" / "pginspect_probe.sql"

_DSN = os.environ.get("PGINSPECT_TEST_DSN", "").strip()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "safety: adversarial write-enforcement tests")


def _require_dsn() -> str:
    if not _DSN:
        pytest.skip(
            "PGINSPECT_TEST_DSN unset; safety write-probes require a live PostgreSQL "
            "(set by GHA services or local Docker)."
        )
    return _DSN


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    return _require_dsn()


@pytest.fixture(scope="session")
def pg_endpoint(pg_dsn: str) -> dict[str, str | int]:
    return parse_dsn(pg_dsn)


@pytest.fixture(scope="session", autouse=True)
def _apply_probe_fixture(pg_dsn: str, pg_endpoint: dict[str, str | int]) -> None:
    sql = FIXTURE_SQL.read_text(encoding="utf-8")
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute(sql)
        expected_major = os.environ.get("PGINSPECT_EXPECT_PG_MAJOR", "").strip()
        if expected_major:
            row = conn.execute("SHOW server_version_num").fetchone()
            assert row is not None
            major = int(row[0]) // 10000
            assert major == int(expected_major)
    assert_subject_has_write_grants(pg_endpoint)


@pytest.fixture
def subject_password_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGPASSWORD", SUBJECT_PASSWORD)


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
