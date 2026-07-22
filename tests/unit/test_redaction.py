"""Tests for redaction primitives (no renderers)."""

from __future__ import annotations

import os
from pathlib import Path

from pginspect.redaction import (
    build_safe_debug_frames,
    fingerprint_explicit_host,
    sanitize_untrusted_text,
)

CANARY_PASSWORD = "CANARY_PASSWORD_7f03"
CANARY_HOST = "secret-db.internal.example"
CANARY_DSN = f"postgresql://private_role:{CANARY_PASSWORD}@{CANARY_HOST}:5432/private_database"
CANARY_PASSFILE = "/home/alice/.pgpass"
CANARY_CERT = "/srv/private/client.key"


def test_host_fingerprint_format() -> None:
    fp = fingerprint_explicit_host("Db.Example")
    assert fp.startswith("sha256:")
    assert len(fp) == len("sha256:") + 16
    assert all(c in "0123456789abcdef" for c in fp.removeprefix("sha256:"))


def test_fingerprint_is_case_sensitive_and_does_not_lowercase() -> None:
    assert fingerprint_explicit_host("A") != fingerprint_explicit_host("a")


def test_fingerprint_never_returns_raw_host() -> None:
    assert CANARY_HOST not in fingerprint_explicit_host(CANARY_HOST)
    assert fingerprint_explicit_host(f"  {CANARY_HOST}  ") == fingerprint_explicit_host(CANARY_HOST)


def test_sanitize_strips_canaries() -> None:
    dirty = (
        f"password={CANARY_PASSWORD} host={CANARY_HOST} dsn={CANARY_DSN} "
        f"passfile={CANARY_PASSFILE} cert={CANARY_CERT}"
    )
    cleaned = sanitize_untrusted_text(dirty)
    assert CANARY_PASSWORD not in cleaned
    assert CANARY_HOST not in cleaned
    assert CANARY_DSN not in cleaned
    assert CANARY_PASSFILE not in cleaned
    assert CANARY_CERT not in cleaned
    assert sanitize_untrusted_text(cleaned) == cleaned


def test_sanitize_bounds_length() -> None:
    long = "x" * 10_000
    out = sanitize_untrusted_text(long)
    assert len(out) <= 513


def test_build_safe_debug_frames_no_home_paths_or_locals() -> None:
    def _raise() -> None:
        raise RuntimeError("boom")

    try:
        _raise()
    except RuntimeError as exc:
        frames = build_safe_debug_frames(exc)

    assert frames
    home = str(Path.home())
    serialized = " ".join(f"{f.module} {f.function} {f.line}" for f in frames)
    assert home not in serialized
    assert "CANARY" not in serialized
    assert "f_locals" not in serialized
    # Windows-style user path fragment
    assert os.path.expanduser("~") not in serialized or os.path.expanduser("~") in {
        ".",
        "",
    }
    for frame in frames:
        assert "/" not in frame.module or frame.module.startswith("pginspect")
        # Absolute Windows paths like C:\Users\... must not appear.
        assert ":\\" not in frame.module
        assert not frame.module.startswith("/")
