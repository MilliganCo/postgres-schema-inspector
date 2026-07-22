"""Build public ConnectionContext / target context from discovery + config."""

from __future__ import annotations

from pginspect.capabilities import DiscoveredCapabilities, extension_availability_map
from pginspect.config import ConnectionConfig
from pginspect.models.context import (
    ConnectionContext,
    ConnectionTargetContext,
    KnownExtensionSnapshot,
)
from pginspect.models.enums import ConnectionTargetSource
from pginspect.redaction import fingerprint_explicit_host
from pginspect.version_policy import classify_server_version


def build_target_context(connection: ConnectionConfig) -> ConnectionTargetContext:
    """Fingerprint explicit CLI host intent; otherwise libpq-resolved unknown."""
    if connection.host is not None:
        return ConnectionTargetContext(
            explicit_host_fingerprint=fingerprint_explicit_host(connection.host),
            source=ConnectionTargetSource.EXPLICIT_CLI_HOST,
        )
    return ConnectionTargetContext(
        explicit_host_fingerprint=None,
        source=ConnectionTargetSource.LIBPQ_RESOLVED_UNKNOWN,
    )


def build_connection_context(
    discovered: DiscoveredCapabilities,
    connection: ConnectionConfig,
) -> ConnectionContext:
    """Assemble public ConnectionContext from private discovery + connection intent."""
    support = classify_server_version(discovered.server_version, discovered.server_version_num)
    ext_map = extension_availability_map(discovered.installed_extensions)
    return ConnectionContext(
        database=discovered.database_name,
        role=discovered.current_role,
        session_user=discovered.session_user,
        server_version=discovered.server_version,
        server_version_num=discovered.server_version_num,
        server_major=discovered.server_major,
        server_major_label=discovered.server_major_label,
        version_support=support,
        in_recovery=discovered.in_recovery,
        target=build_target_context(connection),
        privileges=discovered.privileges,
        extensions=KnownExtensionSnapshot(
            hypopg=ext_map["hypopg"],
            pg_stat_statements=ext_map["pg_stat_statements"],
            pgstattuple=ext_map["pgstattuple"],
            pg_buffercache=ext_map["pg_buffercache"],
        ),
    )
