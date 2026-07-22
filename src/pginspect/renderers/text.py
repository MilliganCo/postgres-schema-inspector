"""Text renderer and terminal escaping for CommandResult."""

from __future__ import annotations

from pginspect.models.enums import FindingId, VersionSupportStatus
from pginspect.models.finding import (
    ConnectionFailedFinding,
    SessionSafetyMisconfiguredFinding,
    SessionSafetyVerifiedFinding,
)
from pginspect.models.result import CommandResult, ConnectTestCommandResult, VersionCommandResult

# C1 controls + DEL; bidi / directionality / line separators that can reshape terminal output.
_BIDI_AND_SEPARATORS: frozenset[int] = frozenset(
    {
        0x061C,  # Arabic Letter Mark
        0x200E,  # LRM
        0x200F,  # RLM
        0x202A,  # LRE
        0x202B,  # RLE
        0x202C,  # PDF
        0x202D,  # LRO
        0x202E,  # RLO
        0x2028,  # Line Separator
        0x2029,  # Paragraph Separator
        0x2066,  # LRI
        0x2067,  # RLI
        0x2068,  # FSI
        0x2069,  # PDI
    }
)

_VERSION_SUPPORT_LABELS: dict[VersionSupportStatus, str] = {
    VersionSupportStatus.SUPPORTED: "supported",
    VersionSupportStatus.EXPERIMENTAL: "experimental",
    VersionSupportStatus.UNTESTED_NEWER: "untested_newer",
    VersionSupportStatus.UNSUPPORTED_OLDER: "unsupported_older",
    VersionSupportStatus.UNSUPPORTED_LEGACY: "unsupported_legacy",
}


def escape_terminal_value(value: str) -> str:
    """Escape C0/C1 controls, DEL, ESC, CR/LF/TAB, U+2028/U+2029, and Unicode bidi controls.

    Preserve normal printable Unicode. User values must never be treated as Rich markup.
    """
    parts: list[str] = []
    for ch in value:
        code = ord(ch)
        if ch == "\n":
            parts.append("\\n")
        elif ch == "\r":
            parts.append("\\r")
        elif ch == "\t":
            parts.append("\\t")
        elif code < 0x20 or code == 0x7F or 0x80 <= code <= 0x9F:
            parts.append(f"\\x{code:02x}")
        elif code in _BIDI_AND_SEPARATORS:
            parts.append(f"\\u{code:04x}")
        else:
            parts.append(ch)
    return "".join(parts)


def render_text(result: CommandResult) -> str:
    """Render ``result`` as line-oriented English text (no ``Exit: N`` line)."""
    if isinstance(result, VersionCommandResult):
        return f"pginspect {result.app_version}\n"
    if isinstance(result, ConnectTestCommandResult):
        return _render_connect_test(result)
    raise TypeError(f"unsupported CommandResult type: {type(result)!r}")


def render_text_debug(result: CommandResult) -> str | None:
    """Render structured debug section for stderr, or ``None`` when absent."""
    error = getattr(result, "error", None)
    if error is None or error.debug is None:
        return None
    debug = error.debug
    lines: list[str] = [
        "Debug:",
        f"  exception_type: {escape_terminal_value(debug.exception_type)}",
    ]
    if debug.causal_chain_types:
        chain = ", ".join(escape_terminal_value(t) for t in debug.causal_chain_types)
        lines.append(f"  causal_chain: {chain}")
    for frame in debug.frames:
        module = escape_terminal_value(frame.module)
        function = escape_terminal_value(frame.function)
        lines.append(f"  {module}.{function}:{frame.line}")
    return "\n".join(lines) + "\n"


def _render_connect_test(result: ConnectTestCommandResult) -> str:
    lines: list[str] = []
    failed = _find_failed(result)
    misconfigured = _find_misconfigured(result)
    verified = _find_verified(result)
    context = result.context

    if failed is not None:
        lines.append("Connection: failed")
        if result.error is not None:
            lines.append(f"Error: {escape_terminal_value(result.error.message)}")
        text = "\n".join(lines) + "\n"
        assert "Exit:" not in text
        return text

    lines.append("Connection: established")

    if context is not None:
        lines.append(f"Database: {escape_terminal_value(context.database)}")
        lines.append(f"Role: {escape_terminal_value(context.role)}")
        if context.session_user == context.role:
            lines.append("Session user: same as current role")
        else:
            lines.append(f"Session user: {escape_terminal_value(context.session_user)}")
        support = _VERSION_SUPPORT_LABELS.get(
            context.version_support, context.version_support.value
        )
        lines.append(f"Server: {escape_terminal_value(context.server_version)} ({support})")
        lines.append(f"In recovery: {'yes' if context.in_recovery else 'no'}")

    if misconfigured is not None:
        lines.append("Session safety: MISCONFIGURED")
        mis_evidence = misconfigured.evidence
        expected = mis_evidence.expected
        lines.append(
            "Timeouts: "
            f"statement={expected.statement_timeout_ms}ms "
            f"lock={expected.lock_timeout_ms}ms "
            f"idle_xact={expected.idle_in_transaction_session_timeout_ms}ms"
        )
        lines.append("Write probe: not run")
        lines.append(f"Category: {mis_evidence.category.value}")
        if mis_evidence.observed is not None:
            observed = mis_evidence.observed
            lines.append(
                "Expected timeouts: "
                f"statement={expected.statement_timeout_ms}ms "
                f"lock={expected.lock_timeout_ms}ms "
                f"idle_xact={expected.idle_in_transaction_session_timeout_ms}ms"
            )
            lines.append(
                "Observed timeouts: "
                f"statement={observed.statement_timeout_ms}ms "
                f"lock={observed.lock_timeout_ms}ms "
                f"idle_xact={observed.idle_in_transaction_session_timeout_ms}ms"
            )
    elif verified is not None:
        lines.append("Session safety: verified")
        verified_evidence = verified.evidence
        lines.append(
            "Timeouts: "
            f"statement={verified_evidence.statement_timeout_ms}ms "
            f"lock={verified_evidence.lock_timeout_ms}ms "
            f"idle_xact={verified_evidence.idle_in_transaction_session_timeout_ms}ms"
        )
        lines.append("Write probe: not run")
        # Spec wording: read-only configuration verified; do not claim role cannot write.
        lines.append("Read-only configuration verified. No write probe was executed.")
    else:
        lines.append("Session safety: unknown")
        lines.append("Write probe: not run")

    if context is not None:
        lines.append("Extensions:")
        ext = context.extensions
        lines.append(f"  hypopg: {ext.hypopg.value}")
        lines.append(f"  pg_stat_statements: {ext.pg_stat_statements.value}")
        lines.append(f"  pgstattuple: {ext.pgstattuple.value}")
        lines.append(f"  pg_buffercache: {ext.pg_buffercache.value}")

    if result.error is not None:
        lines.append(f"Error: {escape_terminal_value(result.error.message)}")

    # Non-healthy version findings: surface title when present and not OK path.
    for finding in result.findings:
        if finding.id in {
            FindingId.CONNECTION_SERVER_VERSION_EXPERIMENTAL,
            FindingId.CONNECTION_SERVER_VERSION_UNTESTED,
            FindingId.CONNECTION_SERVER_VERSION_UNSUPPORTED,
        }:
            lines.append(f"Finding: {escape_terminal_value(finding.title)}")
            if finding.summary:
                lines.append(f"  {escape_terminal_value(finding.summary)}")

    text = "\n".join(lines) + "\n"
    assert "Exit:" not in text
    return text


def _find_failed(result: ConnectTestCommandResult) -> ConnectionFailedFinding | None:
    for finding in result.findings:
        if isinstance(finding, ConnectionFailedFinding):
            return finding
    return None


def _find_misconfigured(
    result: ConnectTestCommandResult,
) -> SessionSafetyMisconfiguredFinding | None:
    for finding in result.findings:
        if isinstance(finding, SessionSafetyMisconfiguredFinding):
            return finding
    return None


def _find_verified(result: ConnectTestCommandResult) -> SessionSafetyVerifiedFinding | None:
    for finding in result.findings:
        if isinstance(finding, SessionSafetyVerifiedFinding):
            return finding
    return None
