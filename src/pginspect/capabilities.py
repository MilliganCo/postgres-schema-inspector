"""Atomic capability discovery via DiagnosticSession (private snapshot)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, LiteralString

from pginspect.exceptions import PginspectInternalError
from pginspect.models.context import PrivilegeSnapshot
from pginspect.models.enums import ExtensionAvailability
from pginspect.session import SessionState
from pginspect.version_policy import server_major_from_num, server_major_label

if TYPE_CHECKING:
    from pginspect.session import DiagnosticSession

KNOWN_EXTENSIONS: tuple[str, ...] = (
    "hypopg",
    "pg_stat_statements",
    "pgstattuple",
    "pg_buffercache",
)

CAPABILITY_DISCOVERY_SQL: LiteralString = """
SELECT
    pg_catalog.current_database()::text AS database_name,
    CURRENT_USER::text AS current_role,
    SESSION_USER::text AS session_user,
    pg_catalog.current_setting('server_version') AS server_version,
    pg_catalog.current_setting('server_version_num')::integer AS server_version_num,
    pg_catalog.pg_is_in_recovery() AS in_recovery,
    pg_catalog.pg_has_role(CURRENT_USER, 'pg_monitor', 'USAGE') AS can_use_pg_monitor,
    pg_catalog.pg_has_role(CURRENT_USER, 'pg_read_all_stats', 'USAGE')
        AS can_use_pg_read_all_stats,
    pg_catalog.pg_has_role(CURRENT_USER, 'pg_read_all_settings', 'USAGE')
        AS can_use_pg_read_all_settings,
    (
        SELECT r.rolsuper
        FROM pg_catalog.pg_roles AS r
        WHERE r.rolname = CURRENT_USER
    ) AS is_superuser,
    ARRAY(
        SELECT e.extname
        FROM pg_catalog.pg_extension AS e
        WHERE e.extname = ANY (%s::text[])
        ORDER BY e.extname
    ) AS installed_known_extensions
"""


@dataclass(frozen=True)
class DiscoveredCapabilities:
    """Private, non-serialized capability snapshot (never passed to renderers)."""

    database_name: str
    current_role: str
    session_user: str
    server_version: str
    server_version_num: int
    server_major: int | None
    server_major_label: str
    in_recovery: bool
    privileges: PrivilegeSnapshot
    installed_extensions: frozenset[str]


def extension_availability_map(
    installed: frozenset[str],
) -> dict[str, ExtensionAvailability]:
    """Deterministic mapping for every allowlisted known extension."""
    return {
        name: (
            ExtensionAvailability.AVAILABLE
            if name in installed
            else ExtensionAvailability.UNAVAILABLE
        )
        for name in KNOWN_EXTENSIONS
    }


def discover_capabilities(session: DiagnosticSession) -> DiscoveredCapabilities:
    """Run one atomic discovery SELECT; require session.state == READY."""
    if session.state is not SessionState.READY:
        raise PginspectInternalError("discover_capabilities requires session state READY")

    row = session._fetch_one(CAPABILITY_DISCOVERY_SQL, (list(KNOWN_EXTENSIONS),))

    try:
        database_name = str(row["database_name"] or "")
        current_role = str(row["current_role"] or "")
        session_user = str(row["session_user"] or "")
        server_version = str(row["server_version"] or "")
        version_num_raw = row["server_version_num"]
        if not isinstance(version_num_raw, int):
            version_num_raw = int(str(version_num_raw))
        server_version_num = version_num_raw
        in_recovery = bool(row["in_recovery"])
        can_monitor = bool(row["can_use_pg_monitor"])
        can_stats = bool(row["can_use_pg_read_all_stats"])
        can_settings = bool(row["can_use_pg_read_all_settings"])
        is_superuser_raw = row["is_superuser"]
        installed_raw = row["installed_known_extensions"]
    except (KeyError, TypeError, ValueError) as exc:
        raise PginspectInternalError(
            "capability discovery returned unexpected shape",
        ) from exc

    if not database_name or not current_role or not session_user or not server_version:
        raise PginspectInternalError("capability discovery returned empty required identity fields")
    if server_version_num <= 0:
        raise PginspectInternalError("capability discovery returned non-positive server_version_num")
    if is_superuser_raw is None:
        raise PginspectInternalError("is_superuser must not be NULL")

    if isinstance(installed_raw, (list, tuple)):
        installed = frozenset(str(x) for x in installed_raw)
    else:
        raise PginspectInternalError("installed_known_extensions has unexpected type")

    if not installed.issubset(frozenset(KNOWN_EXTENSIONS)):
        raise PginspectInternalError("installed extensions not a subset of allowlist")

    return DiscoveredCapabilities(
        database_name=database_name,
        current_role=current_role,
        session_user=session_user,
        server_version=server_version,
        server_version_num=server_version_num,
        server_major=server_major_from_num(server_version_num),
        server_major_label=server_major_label(server_version_num, server_version),
        in_recovery=in_recovery,
        privileges=PrivilegeSnapshot(
            is_superuser=bool(is_superuser_raw),
            can_use_pg_monitor=can_monitor,
            can_use_pg_read_all_stats=can_stats,
            can_use_pg_read_all_settings=can_settings,
        ),
        installed_extensions=installed,
    )
