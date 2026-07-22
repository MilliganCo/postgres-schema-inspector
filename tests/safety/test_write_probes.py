"""Write-probe safety suite: fresh DiagnosticSession per adversarial statement."""

from __future__ import annotations

import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.connection import open_connection
from pginspect.session import DiagnosticSession

from tests.safety._adversarial_sql import ADVERSARIAL_PROBES, READONLY_SQLSTATE
from tests.safety._helpers import (
    SENTINEL_PAYLOAD,
    count_adversarial_tables,
    read_sentinel,
)

pytestmark = pytest.mark.safety


@pytest.mark.parametrize(
    ("probe_name", "sql"),
    ADVERSARIAL_PROBES,
    ids=[name for name, _sql in ADVERSARIAL_PROBES],
)
def test_write_probe_rejected_with_25006(
    probe_name: str,
    sql: str,
    subject_connection_config: ConnectionConfig,
    pg_endpoint: dict[str, str | int],
) -> None:
    """F-06/F-07: each probe uses a fresh session; observer sees unchanged sentinel."""
    before = read_sentinel(pg_endpoint)
    assert before == SENTINEL_PAYLOAD
    tables_before = count_adversarial_tables(pg_endpoint)

    with open_connection(subject_connection_config) as conn:
        with DiagnosticSession(conn, SessionSafetyConfig()) as session:
            assert session.verification_evidence.transaction_read_only is True
            with pytest.raises(Exception) as exc_info:
                # Test-only: exercise adversarial SQL on the established connection.
                session._connection.execute(sql)  # noqa: SLF001
            sqlstate = getattr(exc_info.value, "sqlstate", None)
            assert sqlstate == READONLY_SQLSTATE, (
                f"probe {probe_name!r} expected {READONLY_SQLSTATE}, got {sqlstate!r} "
                f"({exc_info.value!r})"
            )

    after = read_sentinel(pg_endpoint)
    assert after == SENTINEL_PAYLOAD
    assert count_adversarial_tables(pg_endpoint) == tables_before


@pytest.mark.parametrize(
    ("probe_name", "sql"),
    ADVERSARIAL_PROBES,
    ids=[f"reconnect-{name}" for name, _sql in ADVERSARIAL_PROBES],
)
def test_write_probe_rejected_after_reconnect(
    probe_name: str,
    sql: str,
    subject_connection_config: ConnectionConfig,
    pg_endpoint: dict[str, str | int],
) -> None:
    """Repeat each probe on a brand-new connection after the first rejection."""
    with open_connection(subject_connection_config) as conn:
        with DiagnosticSession(conn, SessionSafetyConfig()) as session:
            with pytest.raises(Exception) as first:
                session._connection.execute(sql)  # noqa: SLF001
            assert getattr(first.value, "sqlstate", None) == READONLY_SQLSTATE

    with open_connection(subject_connection_config) as conn2:
        with DiagnosticSession(conn2, SessionSafetyConfig()) as session2:
            with pytest.raises(Exception) as second:
                session2._connection.execute(sql)  # noqa: SLF001
            assert getattr(second.value, "sqlstate", None) == READONLY_SQLSTATE

    assert read_sentinel(pg_endpoint) == SENTINEL_PAYLOAD
