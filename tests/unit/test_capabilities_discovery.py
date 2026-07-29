"""Coverage for capability discovery validation paths."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pginspect.capabilities import discover_capabilities
from pginspect.exceptions import PginspectInternalError
from pginspect.session import SessionState


def _ready_session(row: dict[str, object]) -> MagicMock:
    session = MagicMock()
    session.state = SessionState.READY
    session._fetch_one.return_value = row
    return session


def _base_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "database_name": "shop",
        "current_role": "monitor",
        "session_user": "monitor",
        "server_version": "18.4",
        "server_version_num": 180004,
        "in_recovery": False,
        "can_use_pg_monitor": True,
        "can_use_pg_read_all_stats": True,
        "can_use_pg_read_all_settings": False,
        "is_superuser": False,
        "installed_known_extensions": [],
    }
    row.update(overrides)
    return row


def test_discover_requires_ready_state() -> None:
    session = MagicMock()
    session.state = SessionState.NEW
    with pytest.raises(PginspectInternalError, match="READY"):
        discover_capabilities(session)


def test_discover_coerces_version_num_string() -> None:
    caps = discover_capabilities(_ready_session(_base_row(server_version_num="180004")))
    assert caps.server_version_num == 180004


def test_discover_bad_shape() -> None:
    with pytest.raises(PginspectInternalError, match="unexpected shape"):
        discover_capabilities(_ready_session({"database_name": "shop"}))


def test_discover_empty_identity() -> None:
    with pytest.raises(PginspectInternalError, match="empty required"):
        discover_capabilities(_ready_session(_base_row(database_name="")))


def test_discover_non_positive_version_num() -> None:
    with pytest.raises(PginspectInternalError, match="non-positive"):
        discover_capabilities(_ready_session(_base_row(server_version_num=0)))


def test_discover_null_superuser() -> None:
    with pytest.raises(PginspectInternalError, match="is_superuser"):
        discover_capabilities(_ready_session(_base_row(is_superuser=None)))


def test_discover_bad_extensions_type() -> None:
    with pytest.raises(PginspectInternalError, match="installed_known_extensions"):
        discover_capabilities(_ready_session(_base_row(installed_known_extensions="hypopg")))


def test_discover_extensions_outside_allowlist() -> None:
    with pytest.raises(PginspectInternalError, match="subset of allowlist"):
        discover_capabilities(
            _ready_session(_base_row(installed_known_extensions=["not_allowlisted"]))
        )


def test_discover_success_with_installed() -> None:
    caps = discover_capabilities(
        _ready_session(_base_row(installed_known_extensions=["hypopg", "pgstattuple"]))
    )
    assert caps.installed_extensions == frozenset({"hypopg", "pgstattuple"})
    assert caps.database_name == "shop"
