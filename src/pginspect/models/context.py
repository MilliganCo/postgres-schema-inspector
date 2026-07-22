"""Public connection context models."""

from __future__ import annotations

from pginspect.models.base import PublicModel
from pginspect.models.enums import (
    ConnectionTargetSource,
    ExtensionAvailability,
    VersionSupportStatus,
)


class ConnectionTargetContext(PublicModel):
    explicit_host_fingerprint: str | None
    source: ConnectionTargetSource


class PrivilegeSnapshot(PublicModel):
    is_superuser: bool
    can_use_pg_monitor: bool
    can_use_pg_read_all_stats: bool
    can_use_pg_read_all_settings: bool


class KnownExtensionSnapshot(PublicModel):
    hypopg: ExtensionAvailability
    pg_stat_statements: ExtensionAvailability
    pgstattuple: ExtensionAvailability
    pg_buffercache: ExtensionAvailability


class ConnectionContext(PublicModel):
    database: str
    role: str
    session_user: str
    server_version: str
    server_version_num: int
    server_major: int | None
    server_major_label: str
    version_support: VersionSupportStatus
    in_recovery: bool
    target: ConnectionTargetContext
    privileges: PrivilegeSnapshot
    extensions: KnownExtensionSnapshot
