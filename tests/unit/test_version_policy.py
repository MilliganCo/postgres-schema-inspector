"""Tests for version support policy classification."""

from __future__ import annotations

import pytest

from pginspect.models.enums import VersionSupportStatus
from pginspect.version_policy import (
    MAX_TESTED_STABLE_MAJOR,
    MIN_SUPPORTED_MAJOR,
    classify_server_version,
)


@pytest.mark.parametrize(
    ("num", "label", "expected"),
    [
        (180004, "18.4", VersionSupportStatus.SUPPORTED),
        (190000, "19beta2", VersionSupportStatus.EXPERIMENTAL),
        (190000, "19.0", VersionSupportStatus.UNTESTED_NEWER),
        (130008, "13.8", VersionSupportStatus.UNSUPPORTED_OLDER),
        (90624, "9.6.24", VersionSupportStatus.UNSUPPORTED_LEGACY),
        (140000, "14.0", VersionSupportStatus.SUPPORTED),
        (170003, "17.3", VersionSupportStatus.SUPPORTED),
        (200000, "20.0", VersionSupportStatus.UNTESTED_NEWER),
        (190000, "19rc1", VersionSupportStatus.EXPERIMENTAL),
        (100018, "10.18", VersionSupportStatus.UNSUPPORTED_OLDER),
    ],
)
def test_classify(num: int, label: str, expected: VersionSupportStatus) -> None:
    assert classify_server_version(label, num) is expected


def test_policy_constants() -> None:
    assert MIN_SUPPORTED_MAJOR == 14
    assert MAX_TESTED_STABLE_MAJOR == 18
