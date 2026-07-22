"""Light tests for capability discovery SQL constants and allowlist."""

from __future__ import annotations

from pginspect.capabilities import (
    CAPABILITY_DISCOVERY_SQL,
    KNOWN_EXTENSIONS,
    extension_availability_map,
)
from pginspect.models.enums import ExtensionAvailability


def test_capability_sql_uses_special_forms_not_qualified_current_user() -> None:
    sql = CAPABILITY_DISCOVERY_SQL
    assert "CURRENT_USER" in sql
    assert "SESSION_USER" in sql
    assert "pg_catalog.current_user" not in sql.lower()
    assert "pg_catalog.session_user" not in sql.lower()
    assert "pg_catalog.current_setting('server_version')" in sql
    assert "pg_catalog.current_setting('server_version_num')" in sql
    assert "version()" not in sql
    assert "pg_catalog.version" not in sql


def test_known_extensions_order_and_completeness() -> None:
    assert KNOWN_EXTENSIONS == (
        "hypopg",
        "pg_stat_statements",
        "pgstattuple",
        "pg_buffercache",
    )


def test_extension_availability_map_deterministic() -> None:
    mapping = extension_availability_map(frozenset({"hypopg"}))
    assert list(mapping.keys()) == list(KNOWN_EXTENSIONS)
    assert mapping["hypopg"] is ExtensionAvailability.AVAILABLE
    assert mapping["pg_stat_statements"] is ExtensionAvailability.UNAVAILABLE
    assert mapping["pgstattuple"] is ExtensionAvailability.UNAVAILABLE
    assert mapping["pg_buffercache"] is ExtensionAvailability.UNAVAILABLE
