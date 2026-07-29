"""Extra coverage for redaction frame fallbacks and sanitize edges."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from pginspect.redaction import (
    _frame_module_name,
    build_safe_debug_frames,
    sanitize_untrusted_text,
)


def test_sanitize_empty_string() -> None:
    assert sanitize_untrusted_text("") == ""


def test_frame_module_name_from_globals() -> None:
    frame = SimpleNamespace(f_globals={"__name__": "pginspect.session"})
    assert _frame_module_name(frame) == "pginspect.session"


def test_frame_module_name_basename_fallback() -> None:
    code = SimpleNamespace(co_filename="session.py")
    frame = SimpleNamespace(f_globals={}, f_code=code)
    assert _frame_module_name(frame) == "session.py"


def test_frame_module_name_absolute_path_unknown() -> None:
    code = SimpleNamespace(co_filename=r"C:\Users\Cody\project\session.py")
    frame = SimpleNamespace(f_globals={"__name__": ""}, f_code=code)
    assert _frame_module_name(frame) == "<unknown>"


def test_frame_module_name_missing_code() -> None:
    frame = SimpleNamespace(f_globals=None, f_code=None)
    assert _frame_module_name(frame) == "<unknown>"


def test_build_safe_debug_frames_extract_tb_fallback() -> None:
    """Force empty live-frame list so extract_tb fallback path runs."""

    class _ForceEmptyLive:
        """Compare as non-positive max so the live-frame while-loop never runs."""

        def __gt__(self, other: object) -> bool:
            return False

        def __index__(self) -> int:
            return 20

    def _raise() -> None:
        raise RuntimeError("boom")

    try:
        _raise()
    except RuntimeError as exc:
        extracted = [
            SimpleNamespace(filename="/abs/path/mod.py", name="fn", lineno=12),
            SimpleNamespace(filename="relative.py", name="pkg.fn", lineno=3),
            SimpleNamespace(filename=r"C:\abs\mod.py", name="fn", lineno=1),
            SimpleNamespace(filename="", name="plain", lineno=None),
        ]
        with (
            patch("pginspect.redaction._MAX_FRAMES", _ForceEmptyLive()),
            patch("pginspect.redaction.traceback.extract_tb", return_value=extracted),
        ):
            frames = build_safe_debug_frames(exc)

    assert [f.module for f in frames] == ["<unknown>", "relative.py", "<unknown>", "<unknown>"]
    assert frames[1].function == "pkg.fn"
    assert frames[1].line == 3
