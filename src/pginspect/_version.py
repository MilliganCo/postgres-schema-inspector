from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

_FALLBACK = "0.0.0+unknown"


def get_app_version() -> str:
    try:
        return version("postgres-schema-inspector")
    except PackageNotFoundError:
        return _FALLBACK
