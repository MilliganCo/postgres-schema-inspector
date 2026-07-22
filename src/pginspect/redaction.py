"""Security primitives: host fingerprinting, text sanitization, safe debug frames."""

from __future__ import annotations

import hashlib
import re
import traceback
import unicodedata
from typing import Final

from pginspect.models.execution_error import DebugFrame

_MAX_FRAMES: Final[int] = 20
_MAX_SANITIZED_LENGTH: Final[int] = 512
_MAX_TYPE_NAME_LENGTH: Final[int] = 160

# Defense-in-depth patterns for untrusted strings (never treat as permission to keep driver text).
_PASSWORD_ASSIGN = re.compile(r"(?i)(?:password|passwd|pwd|passfile)\s*[:=]\s*[^\s;'\"]+")
_URI = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s]+")
_HOST_ASSIGN = re.compile(r"(?i)\b(?:host|hostname|server)\s*[:=]\s*[^\s;'\"]+")
_HOME_PATH = re.compile(r"(?i)(?:/home/[^/\s]+|/Users/[^/\s]+|C:\\Users\\[^\\\s]+|~[/\\][^\s]*)")
_SENSITIVE_PATH = re.compile(
    r"(?i)(?:[^\s]*\.pgpass|[^\s]*pgpassfile[^\s]*|[^\s]*ssl(?:root)?cert[^\s]*|"
    r"[^\s]*sslkey[^\s]*|[^\s]*client\.key[^\s]*|/srv/[^\s]+)"
)


def fingerprint_explicit_host(host: str) -> str:
    """Pseudonymous fingerprint of an exact `--host` intent string.

    NFC + strip, then ``sha256:`` + first 16 hex chars. No lowercasing, DNS, or multi-host split.
    """
    normalized = unicodedata.normalize("NFC", host.strip())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def sanitize_untrusted_text(text: str) -> str:
    """Redact obvious secrets/paths from untrusted text. Idempotent and length-bounded."""
    if not text:
        return ""
    cleaned = text.replace("\x00", "")
    cleaned = _URI.sub("[redacted-uri]", cleaned)
    cleaned = _PASSWORD_ASSIGN.sub("[redacted]", cleaned)
    cleaned = _HOST_ASSIGN.sub("[redacted-host]", cleaned)
    cleaned = _SENSITIVE_PATH.sub("[redacted-path]", cleaned)
    cleaned = _HOME_PATH.sub("[redacted-path]", cleaned)
    if len(cleaned) > _MAX_SANITIZED_LENGTH:
        cleaned = cleaned[:_MAX_SANITIZED_LENGTH] + "…"
    return cleaned


def _frame_module_name(frame: object) -> str:
    globals_dict = getattr(frame, "f_globals", {}) or {}
    name = globals_dict.get("__name__")
    if isinstance(name, str) and name:
        return name[:_MAX_TYPE_NAME_LENGTH]
    code = getattr(frame, "f_code", None)
    filename = getattr(code, "co_filename", "") if code is not None else ""
    # Never return absolute paths; fall back to a generic label.
    if filename and not any(ch in filename for ch in ("/", "\\", ":")):
        return str(filename)[:_MAX_TYPE_NAME_LENGTH]
    return "<unknown>"


def build_safe_debug_frames(exc: BaseException) -> tuple[DebugFrame, ...]:
    """Extract bounded traceback frames without absolute paths, locals, or source lines."""
    frames: list[DebugFrame] = []
    tb = exc.__traceback__
    extracted = traceback.extract_tb(tb, limit=_MAX_FRAMES) if tb is not None else []

    # Prefer live frame objects when available (module via f_globals).
    live: list[object] = []
    current = tb
    while current is not None and len(live) < _MAX_FRAMES:
        live.append(current.tb_frame)
        current = current.tb_next

    if live:
        for frame_obj in live[:_MAX_FRAMES]:
            code = getattr(frame_obj, "f_code", None)
            function = getattr(code, "co_name", "<unknown>") if code is not None else "<unknown>"
            line = int(getattr(frame_obj, "f_lineno", 0) or 0)
            frames.append(
                DebugFrame(
                    module=_frame_module_name(frame_obj),
                    function=str(function)[:_MAX_TYPE_NAME_LENGTH],
                    line=line,
                )
            )
    else:
        for item in extracted[:_MAX_FRAMES]:
            module = item.name if "." in item.name else "<unknown>"
            # extract_tb gives filename; never expose it as module when absolute.
            filename = item.filename or ""
            if "/" in filename or "\\" in filename or (len(filename) > 1 and filename[1:2] == ":"):
                module_name = "<unknown>"
            else:
                module_name = filename or module
            frames.append(
                DebugFrame(
                    module=module_name[:_MAX_TYPE_NAME_LENGTH],
                    function=str(item.name)[:_MAX_TYPE_NAME_LENGTH],
                    line=int(item.lineno or 0),
                )
            )
    return tuple(frames)
