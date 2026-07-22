"""pginspect release policy for PostgreSQL server version classification."""

from __future__ import annotations

import re

from pginspect.models.enums import VersionSupportStatus

MIN_SUPPORTED_MAJOR = 14
MAX_TESTED_STABLE_MAJOR = 18
TESTED_PRERELEASE_MAJORS: frozenset[int] = frozenset({19})

SUPPORTED_MAJORS: tuple[int, ...] = tuple(range(MIN_SUPPORTED_MAJOR, MAX_TESTED_STABLE_MAJOR + 1))
TESTED_PRERELEASE_MAJORS_TUPLE: tuple[int, ...] = tuple(sorted(TESTED_PRERELEASE_MAJORS))

_PRERELEASE_MARKER = re.compile(r"(?i)(?:alpha|beta|rc)\d*")


def server_major_from_num(server_version_num: int) -> int | None:
    """Return major for PG 10+ numbering; None for pre-10 legacy numbering."""
    if server_version_num < 100_000:
        return None
    return server_version_num // 10_000


def server_major_label(server_version_num: int, server_version: str) -> str:
    major = server_major_from_num(server_version_num)
    if major is not None:
        return str(major)
    # Legacy pre-10: derive a short label from server_version_num when possible.
    if server_version_num >= 90_000:
        # e.g. 90624 → 9.6
        major_part = server_version_num // 10_000
        minor_part = (server_version_num // 100) % 100
        return f"{major_part}.{minor_part}"
    return server_version.split()[0] if server_version else "unknown"


def _is_prerelease_label(server_version: str) -> bool:
    # Strip common suffixes; match beta/rc/alpha markers in the version string.
    return _PRERELEASE_MARKER.search(server_version) is not None


def classify_server_version(server_version: str, server_version_num: int) -> VersionSupportStatus:
    """Classify a server against the checked-in pginspect support policy."""
    if server_version_num < 100_000:
        return VersionSupportStatus.UNSUPPORTED_LEGACY

    major = server_version_num // 10_000

    if MIN_SUPPORTED_MAJOR <= major <= MAX_TESTED_STABLE_MAJOR:
        return VersionSupportStatus.SUPPORTED

    if major in TESTED_PRERELEASE_MAJORS and _is_prerelease_label(server_version):
        return VersionSupportStatus.EXPERIMENTAL

    if major > MAX_TESTED_STABLE_MAJOR:
        return VersionSupportStatus.UNTESTED_NEWER

    # 10–13 (and any gap below MIN_SUPPORTED)
    return VersionSupportStatus.UNSUPPORTED_OLDER
