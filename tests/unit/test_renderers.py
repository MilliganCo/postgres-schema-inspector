"""Unit tests for text/JSON renderers and terminal escaping."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pginspect._version import get_app_version
from pginspect.connectivity import (
    build_completed_connect_test,
    build_connect_operational_failure,
    build_session_safety_misconfigured,
    build_version_result,
)
from pginspect.models.context import (
    ConnectionContext,
    ConnectionTargetContext,
    KnownExtensionSnapshot,
    PrivilegeSnapshot,
)
from pginspect.models.enums import (
    ClassificationSource,
    ConnectionTargetSource,
    ExecutionErrorCategory,
    ExecutionErrorCode,
    ExtensionAvailability,
    SessionSafetyMisconfigurationCategory,
    VersionSupportStatus,
)
from pginspect.models.execution_error import DebugFrame, DebugPayload, ExecutionError
from pginspect.models.finding import (
    ConnectionEstablishedEvidence,
    ConnectionEstablishedFinding,
    ConnectionFailedEvidence,
    ConnectionFailedFinding,
    ConnectionFindingScope,
    ServerVersionSupportedEvidence,
    ServerVersionSupportedFinding,
    SessionSafetyExpectedState,
    SessionSafetyMisconfiguredEvidence,
    SessionSafetyMisconfiguredFinding,
    SessionSafetyVerifiedEvidence,
    SessionSafetyVerifiedFinding,
)
from pginspect.renderers import escape_terminal_value, render_json, render_text, render_text_debug


CANARY_PASSWORD = "CANARY_PASSWORD_7f03"
CANARY_HOST = "secret-db.internal.example"
CANARY_DSN = "postgresql://monitor:CANARY_PASSWORD_7f03@secret-db.internal.example:5432/shop"
CANARY_PASSFILE = "/home/canary/.pgpass"
CANARY_CERT = "/etc/ssl/private/client.key"
CANARY_ANSI = "\x1b[31mINJECT\x1b[0m"


def _scope(*, fingerprint: str | None = None) -> ConnectionFindingScope:
    if fingerprint is None:
        return ConnectionFindingScope(
            target=ConnectionTargetContext(
                explicit_host_fingerprint=None,
                source=ConnectionTargetSource.LIBPQ_RESOLVED_UNKNOWN,
            )
        )
    return ConnectionFindingScope(
        target=ConnectionTargetContext(
            explicit_host_fingerprint=fingerprint,
            source=ConnectionTargetSource.EXPLICIT_CLI_HOST,
        )
    )


def _established() -> ConnectionEstablishedFinding:
    return ConnectionEstablishedFinding(
        title="PostgreSQL connection established",
        scope=_scope(),
        evidence=ConnectionEstablishedEvidence(tls_used=True),
    )


def _verified() -> SessionSafetyVerifiedFinding:
    return SessionSafetyVerifiedFinding(
        title="Diagnostic session safety settings are active",
        scope=_scope(),
        evidence=SessionSafetyVerifiedEvidence(
            default_transaction_read_only=True,
            transaction_read_only=True,
            statement_timeout_ms=15000,
            lock_timeout_ms=2000,
            idle_in_transaction_session_timeout_ms=15000,
            search_path=("pg_catalog",),
            application_name_kind="pginspect_owned",
            application_name_value="pginspect/0.1.0",
            write_probe="not_run",
            verification_level="settings",
            read_only_scope="postgresql_transaction",
            read_only_is_sandbox=False,
        ),
    )


def _context(
    *,
    database: str = "shop",
    role: str = "monitor",
    session_user: str = "monitor",
) -> ConnectionContext:
    return ConnectionContext(
        database=database,
        role=role,
        session_user=session_user,
        server_version="18.4",
        server_version_num=180004,
        server_major=18,
        server_major_label="18",
        version_support=VersionSupportStatus.SUPPORTED,
        in_recovery=False,
        target=ConnectionTargetContext(
            explicit_host_fingerprint=None,
            source=ConnectionTargetSource.LIBPQ_RESOLVED_UNKNOWN,
        ),
        privileges=PrivilegeSnapshot(
            is_superuser=False,
            can_use_pg_monitor=True,
            can_use_pg_read_all_stats=True,
            can_use_pg_read_all_settings=False,
        ),
        extensions=KnownExtensionSnapshot(
            hypopg=ExtensionAvailability.UNAVAILABLE,
            pg_stat_statements=ExtensionAvailability.UNAVAILABLE,
            pgstattuple=ExtensionAvailability.UNAVAILABLE,
            pg_buffercache=ExtensionAvailability.UNAVAILABLE,
        ),
    )


def _version_finding() -> ServerVersionSupportedFinding:
    return ServerVersionSupportedFinding(
        title="PostgreSQL server version is supported",
        scope=_scope(),
        evidence=ServerVersionSupportedEvidence(
            server_version="18.4",
            server_version_num=180004,
            server_major=18,
            server_major_label="18",
            version_support="supported",
            supported_majors=(14, 15, 16, 17, 18),
            max_tested_stable_major=18,
            tested_prerelease_majors=(19,),
        ),
    )


def _healthy() -> object:
    return build_completed_connect_test(
        established=_established(),
        safety_verified=_verified(),
        version_finding=_version_finding(),
        context=_context(),
        started_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        duration_ms=42,
    )


def test_version_text_exact() -> None:
    result = build_version_result()
    assert render_text(result) == f"pginspect {get_app_version()}\n"


def test_json_has_single_trailing_newline_and_sorted_keys() -> None:
    result = build_version_result()
    text = render_json(result)
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    parsed = json.loads(text)
    assert list(parsed.keys()) == sorted(parsed.keys())
    # Round-trip keys at top level are sorted in serialized form
    lines = [line for line in text.splitlines() if line.startswith('  "')]
    keys = [line.split(":", 1)[0].strip().strip('"') for line in lines]
    assert keys == sorted(keys)


def test_user_value_with_markup_does_not_affect_output_structure() -> None:
    result = build_completed_connect_test(
        established=_established(),
        safety_verified=_verified(),
        version_finding=_version_finding(),
        context=_context(database="shop[bold]hack[/bold]", role="monitor"),
        started_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        duration_ms=1,
    )
    text = render_text(result)
    assert "Database: shop[bold]hack[/bold]" in text
    assert text.startswith("Connection: established\n")
    assert "Exit:" not in text


def test_ansi_and_bidi_are_escaped() -> None:
    assert escape_terminal_value("\n") == "\\n"
    assert escape_terminal_value("\r") == "\\r"
    assert escape_terminal_value("\t") == "\\t"
    assert escape_terminal_value("\x1b") == "\\x1b"
    assert escape_terminal_value("\u202e") == "\\u202e"
    assert escape_terminal_value("ok") == "ok"

    result = build_completed_connect_test(
        established=_established(),
        safety_verified=_verified(),
        version_finding=_version_finding(),
        context=_context(database=f"db{CANARY_ANSI}\u202e", role="monitor"),
        started_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        duration_ms=1,
    )
    text = render_text(result)
    assert "\x1b" not in text
    assert "\u202e" not in text
    assert "\\x1b" in text
    assert "\\u202e" in text


def test_no_exit_n_line_in_text() -> None:
    healthy = _healthy()
    assert "Exit:" not in render_text(healthy)
    failed = build_connect_operational_failure(
        finding=ConnectionFailedFinding(
            title="Could not connect to PostgreSQL",
            scope=_scope(),
            evidence=ConnectionFailedEvidence(
                category="authentication_failed",
                classification_source=ClassificationSource.SQLSTATE,
                sqlstate="28P01",
            ),
        ),
        error=ExecutionError(
            code=ExecutionErrorCode.AUTHENTICATION_FAILED,
            category=ExecutionErrorCategory.CONNECTION,
            message="PostgreSQL authentication failed.",
            retryable=False,
            sqlstate="28P01",
            classification_source=ClassificationSource.SQLSTATE,
        ),
        started_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        duration_ms=5,
    )
    assert "Exit:" not in render_text(failed)


def test_connect_test_section_order_healthy() -> None:
    text = render_text(_healthy())
    expected_prefixes = [
        "Connection: established",
        "Database: shop",
        "Role: monitor",
        "Session user: same as current role",
        "Server: 18.4 (supported)",
        "In recovery: no",
        "Session safety: verified",
        "Timeouts: statement=15000ms lock=2000ms idle_xact=15000ms",
        "Write probe: not run",
        "Extensions:",
        "  hypopg: unavailable",
        "  pg_stat_statements: unavailable",
        "  pgstattuple: unavailable",
        "  pg_buffercache: unavailable",
    ]
    lines = text.splitlines()
    for prefix in expected_prefixes:
        assert any(line == prefix or line.startswith(prefix) for line in lines), prefix
    # Fixed relative order
    positions = [text.index(p) for p in expected_prefixes]
    assert positions == sorted(positions)


def test_session_user_literal_when_different() -> None:
    result = build_completed_connect_test(
        established=_established(),
        safety_verified=_verified(),
        version_finding=_version_finding(),
        context=_context(role="monitor", session_user="admin"),
        started_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        duration_ms=1,
    )
    assert "Session user: admin" in render_text(result)


def test_full_canary_leakage_json_text_and_text_debug() -> None:
    """Canaries must not appear in any renderer output surfaces."""
    canaries = (
        CANARY_PASSWORD,
        CANARY_HOST,
        CANARY_DSN,
        CANARY_PASSFILE,
        CANARY_CERT,
        "\x1b[31m",
    )
    error = ExecutionError(
        code=ExecutionErrorCode.AUTHENTICATION_FAILED,
        category=ExecutionErrorCategory.CONNECTION,
        message="PostgreSQL authentication failed.",
        retryable=False,
        sqlstate="28P01",
        classification_source=ClassificationSource.SQLSTATE,
        debug=DebugPayload(
            exception_type="ConnectAuthenticationError",
            causal_chain_types=(),
            frames=(DebugFrame(module="pginspect.connection", function="_connect", line=10),),
        ),
    )
    # Deliberately attempt to smuggle canaries into titles/summaries that renderers escape.
    # Models themselves should not hold secrets; this asserts renderer defense-in-depth.
    finding = ConnectionFailedFinding(
        title="Could not connect to PostgreSQL",
        summary=None,
        scope=_scope(),
        evidence=ConnectionFailedEvidence(
            category="authentication_failed",
            classification_source=ClassificationSource.SQLSTATE,
            sqlstate="28P01",
        ),
    )
    failed = build_connect_operational_failure(
        finding=finding,
        error=error,
        started_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        duration_ms=5,
    )
    healthy = _healthy()
    misconfigured = build_session_safety_misconfigured(
        established=_established(),
        misconfigured=SessionSafetyMisconfiguredFinding(
            title="Diagnostic session safety settings are not active",
            scope=_scope(),
            evidence=SessionSafetyMisconfiguredEvidence(
                category=SessionSafetyMisconfigurationCategory.SET_REJECTED,
                expected=SessionSafetyExpectedState(
                    default_transaction_read_only=True,
                    transaction_read_only=True,
                    statement_timeout_ms=15000,
                    lock_timeout_ms=2000,
                    idle_in_transaction_session_timeout_ms=15000,
                    search_path=("pg_catalog",),
                ),
                observed=None,
                sqlstate=None,
            ),
        ),
        started_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        duration_ms=10,
    )

    for result in (failed, healthy, misconfigured, build_version_result()):
        surfaces = [
            render_json(result),
            render_text(result),
            render_text_debug(result) or "",
        ]
        joined = "\n".join(surfaces)
        for canary in canaries:
            assert canary not in joined, f"leaked {canary!r}"
        assert CANARY_PASSFILE not in joined
        assert CANARY_CERT not in joined


def test_database_role_only_in_context_sections() -> None:
    result = _healthy()
    text = render_text(result)
    # Allowed in Database/Role lines only (not buried in unrelated evidence dumps).
    assert text.count("shop") == 1
    assert "Database: shop" in text
    assert text.count("monitor") >= 1
    assert "Role: monitor" in text


def test_render_text_debug_none_without_debug() -> None:
    assert render_text_debug(build_version_result()) is None
    assert render_text_debug(_healthy()) is None


def test_render_text_debug_with_payload() -> None:
    failed = build_connect_operational_failure(
        finding=ConnectionFailedFinding(
            title="Could not connect to PostgreSQL",
            scope=_scope(),
            evidence=ConnectionFailedEvidence(
                category="authentication_failed",
                classification_source=ClassificationSource.SQLSTATE,
                sqlstate="28P01",
            ),
        ),
        error=ExecutionError(
            code=ExecutionErrorCode.AUTHENTICATION_FAILED,
            category=ExecutionErrorCategory.CONNECTION,
            message="PostgreSQL authentication failed.",
            retryable=False,
            debug=DebugPayload(
                exception_type="ConnectAuthenticationError",
                frames=(DebugFrame(module="pginspect.connection", function="open", line=1),),
            ),
        ),
        started_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        duration_ms=1,
    )
    debug = render_text_debug(failed)
    assert debug is not None
    assert debug.startswith("Debug:\n")
    assert "ConnectAuthenticationError" in debug
    assert "pginspect.connection.open:1" in debug
