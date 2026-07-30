"""Fail-closed diagnostic session: establish, verify, package-owned SQL only."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, LiteralString

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from pginspect._version import get_app_version
from pginspect.config import SessionSafetyConfig
from pginspect.exceptions import (
    ConnectFailedError,
    ConnectNetworkError,
    PginspectInternalError,
    SessionSafetyError,
)
from pginspect.impact.models.result import ImpactConnectionContext
from pginspect.impact.preflight import ResolutionContext
from pginspect.impact.queries import QuerySpec
from pginspect.impact.query_exec import (
    FetchMode,
    QueryExecutionEvent,
    QueryRecorder,
    SessionQueryExecutor,
    execute_allowlisted,
)
from pginspect.impact.query_rows import PreflightRow, ResolutionCaptureRow, SafetyVerifyRow
from pginspect.models.enums import (
    ClassificationSource,
    ExecutionErrorCode,
    SessionSafetyMisconfigurationCategory,
)
from pginspect.models.finding import (
    SessionSafetyExpectedState,
    SessionSafetyObservedState,
    SessionSafetyVerifiedEvidence,
)
from pginspect.redaction import build_safe_debug_frames

ImpactQueryRecorder = Callable[[str, str, tuple[Any, ...], str], None]


def _adapt_impact_recorder(recorder: ImpactQueryRecorder | None) -> QueryRecorder | None:
    """Bridge the positional impact-timeline recorder onto `QueryExecutionEvent`."""
    if recorder is None:
        return None

    def _forward(event: QueryExecutionEvent) -> None:
        recorder(event.query_id, event.sql_text, event.bound_parameters, event.command_kind)

    return _forward


_ESTABLISH_SQL: LiteralString = """
SELECT
    pg_catalog.set_config('default_transaction_read_only', 'on', false),
    pg_catalog.set_config('statement_timeout', %s, false),
    pg_catalog.set_config('lock_timeout', %s, false),
    pg_catalog.set_config('idle_in_transaction_session_timeout', %s, false),
    pg_catalog.set_config('search_path', 'pg_catalog', false)
"""

_VERIFY_SQL: LiteralString = """
SELECT
    pg_catalog.current_setting('default_transaction_read_only')::boolean
        AS default_transaction_read_only,
    pg_catalog.current_setting('transaction_read_only')::boolean
        AS transaction_read_only,
    (
        SELECT setting::bigint
        FROM pg_catalog.pg_settings
        WHERE name = 'statement_timeout'
    ) AS statement_timeout_ms,
    (
        SELECT unit
        FROM pg_catalog.pg_settings
        WHERE name = 'statement_timeout'
    ) AS statement_timeout_unit,
    (
        SELECT setting::bigint
        FROM pg_catalog.pg_settings
        WHERE name = 'lock_timeout'
    ) AS lock_timeout_ms,
    (
        SELECT unit
        FROM pg_catalog.pg_settings
        WHERE name = 'lock_timeout'
    ) AS lock_timeout_unit,
    (
        SELECT setting::bigint
        FROM pg_catalog.pg_settings
        WHERE name = 'idle_in_transaction_session_timeout'
    ) AS idle_in_transaction_session_timeout_ms,
    (
        SELECT unit
        FROM pg_catalog.pg_settings
        WHERE name = 'idle_in_transaction_session_timeout'
    ) AS idle_in_transaction_session_timeout_unit,
    pg_catalog.current_setting('application_name') AS application_name,
    pg_catalog.current_setting('search_path') AS search_path_raw,
    pg_catalog.current_schemas(false) AS effective_search_path
"""


class SessionState(StrEnum):
    NEW = "new"
    ESTABLISHING = "establishing"
    READY = "ready"
    FAILED = "failed"
    CLOSED = "closed"


@dataclass(frozen=True)
class TransportMetadata:
    tls_used: bool | None


@dataclass(frozen=True)
class ImpactSessionState:
    """Result of `DiagnosticSession.establish_impact_profile` (plan Task 4)."""

    resolution_context: ResolutionContext
    connection_context: ImpactConnectionContext
    catalog_snapshot_at: datetime


def observe_transport_metadata(connection: Connection[Any]) -> TransportMetadata:
    """Observe TLS usage without reading password/DSN/get_parameters/repr surfaces."""
    try:
        pgconn = connection.pgconn
        if pgconn is None:
            return TransportMetadata(tls_used=None)
        return TransportMetadata(tls_used=bool(pgconn.ssl_in_use))
    except Exception:
        return TransportMetadata(tls_used=None)


def _expected_state(config: SessionSafetyConfig) -> SessionSafetyExpectedState:
    return SessionSafetyExpectedState(
        default_transaction_read_only=True,
        transaction_read_only=True,
        statement_timeout_ms=config.statement_timeout_ms,
        lock_timeout_ms=config.lock_timeout_ms,
        idle_in_transaction_session_timeout_ms=config.idle_in_transaction_session_timeout_ms,
        search_path=("pg_catalog",),
    )


def _classify_application_name(value: str) -> tuple[str, str | None]:
    if value == "":
        return "empty", None
    owned_prefix = "pginspect/"
    if value.startswith(owned_prefix) and value == f"pginspect/{get_app_version()}":
        return "pginspect_owned", value
    # Also accept any pginspect/<version> as owned (version may differ in edge cases).
    if value.startswith(owned_prefix) and len(value) > len(owned_prefix):
        return "pginspect_owned", value
    return "custom", None


def _map_session_sql_error(exc: psycopg.Error) -> Exception:
    frames = build_safe_debug_frames(exc)
    sqlstate = getattr(exc, "sqlstate", None)
    sqlstate_str = sqlstate if isinstance(sqlstate, str) else None
    driver_type = type(exc).__name__
    if sqlstate_str and sqlstate_str.startswith("08"):
        return ConnectNetworkError(
            code=ExecutionErrorCode.NETWORK_UNREACHABLE,
            classification_source=ClassificationSource.SQLSTATE,
            sqlstate=sqlstate_str,
            driver_exception_type=driver_type,
            debug_frames=frames,
        )
    if sqlstate_str == "57014":
        return ConnectFailedError(
            code=ExecutionErrorCode.OPERATIONAL_FAILURE,
            classification_source=ClassificationSource.SQLSTATE,
            sqlstate=sqlstate_str,
            driver_exception_type=driver_type,
            debug_frames=frames,
        )
    if isinstance(exc, psycopg.OperationalError):
        return ConnectFailedError(
            code=ExecutionErrorCode.OPERATIONAL_FAILURE,
            classification_source=ClassificationSource.FALLBACK_OTHER,
            sqlstate=sqlstate_str,
            driver_exception_type=driver_type,
            debug_frames=frames,
        )
    # Programming / unexpected SQL shape → internal
    return PginspectInternalError(
        "diagnostic session SQL failed",
        debug_frames=frames,
        driver_exception_type=driver_type,
    )


_EXPECTED_IMPACT_ISOLATION = "repeatable read"
_HARDENED_SEARCH_PATH: tuple[str, ...] = ("pg_catalog",)


def _normalize_isolation(value: object) -> str:
    """PostgreSQL reports isolation as free-form text; compare case/space-insensitively."""
    return " ".join(str(value).strip().lower().split())


def _verify_impact_safety_row(row: SafetyVerifyRow, config: SessionSafetyConfig) -> None:
    """Reject an impact session whose hardened state was not actually observed.

    Runs after ``impact.harden_search_path`` and before
    ``impact.preflight_reads``: every mismatch aborts the timeline through the
    Foundation ``SessionSafetyError`` / ``VERIFICATION_MISMATCH`` mechanism, so
    no catalog read is ever issued against an unverified session.
    """
    expected = _expected_state(config)

    # The impact profile scopes read-only to the transaction (BEGIN READ ONLY),
    # so `transaction_read_only` is the authoritative read-only observation for
    # both fields of the Foundation observed-state contract.
    observed = SessionSafetyObservedState(
        default_transaction_read_only=row.transaction_read_only,
        transaction_read_only=row.transaction_read_only,
        statement_timeout_ms=row.statement_timeout_ms,
        lock_timeout_ms=row.lock_timeout_ms,
        idle_in_transaction_session_timeout_ms=row.idle_in_transaction_session_timeout_ms,
        search_path=row.effective_search_path,
    )

    matches = (
        row.transaction_read_only is True
        and _normalize_isolation(row.transaction_isolation) == _EXPECTED_IMPACT_ISOLATION
        and row.effective_search_path == _HARDENED_SEARCH_PATH
        and row.search_path_raw.strip() == _HARDENED_SEARCH_PATH[0]
        and row.statement_timeout_ms == expected.statement_timeout_ms
        and row.lock_timeout_ms == expected.lock_timeout_ms
        and row.idle_in_transaction_session_timeout_ms
        == expected.idle_in_transaction_session_timeout_ms
    )
    if not matches:
        raise SessionSafetyError(
            category=SessionSafetyMisconfigurationCategory.VERIFICATION_MISMATCH,
            expected=expected,
            observed=observed,
            sqlstate=None,
        )


def _build_resolution_context(
    resolution_row: ResolutionCaptureRow,
    preflight_row: PreflightRow,
) -> ResolutionContext:
    return ResolutionContext(
        database=resolution_row.database,
        role=resolution_row.role,
        session_user=resolution_row.session_user,
        current_schema=resolution_row.current_schema,
        current_schemas_user=resolution_row.current_schemas_user,
        current_schemas_with_implicit=resolution_row.current_schemas_with_implicit,
        search_path_raw=resolution_row.search_path_raw,
        max_identifier_length_bytes=resolution_row.max_identifier_length_bytes,
        server_major=preflight_row.server_version_num // 10_000,
        server_version_num=preflight_row.server_version_num,
        keyword_categories=preflight_row.keyword_categories,
    )


def _build_impact_connection_context(
    resolution_row: ResolutionCaptureRow,
    preflight_row: PreflightRow,
) -> ImpactConnectionContext:
    return ImpactConnectionContext(
        server_version=preflight_row.server_version,
        server_version_num=preflight_row.server_version_num,
        server_major=preflight_row.server_version_num // 10_000,
        database=resolution_row.database,
        role=resolution_row.role,
        session_user=resolution_row.session_user,
        current_schema=resolution_row.current_schema,
        search_path_raw=resolution_row.search_path_raw,
        standard_conforming_strings=preflight_row.standard_conforming_strings,
        server_encoding=preflight_row.server_encoding,
        client_encoding=preflight_row.client_encoding,
        transaction_isolation=preflight_row.transaction_isolation,
        transaction_read_only=preflight_row.transaction_read_only,
        in_recovery=preflight_row.in_recovery,
        max_identifier_length=resolution_row.max_identifier_length_bytes,
    )


class DiagnosticSession:
    """Owns SQL execution and a force_rollback transaction after safety establish/verify."""

    def __init__(self, connection: Connection[Any], config: SessionSafetyConfig) -> None:
        self._connection = connection
        self._config = config
        self._state = SessionState.NEW
        self._stack: ExitStack | None = None
        self._verification: SessionSafetyVerifiedEvidence | None = None
        self._entered = False

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def verification_evidence(self) -> SessionSafetyVerifiedEvidence:
        if self._verification is None:
            raise PginspectInternalError("verification evidence unavailable")
        return self._verification

    def transport_metadata(self) -> TransportMetadata:
        """Observe TLS usage without reading password/DSN/get_parameters/repr surfaces."""
        return observe_transport_metadata(self._connection)

    def __enter__(self) -> DiagnosticSession:
        if self._entered or self._state is not SessionState.NEW:
            raise PginspectInternalError("DiagnosticSession cannot be entered twice or reused")
        self._entered = True
        self._state = SessionState.ESTABLISHING
        self._stack = ExitStack()
        self._stack.__enter__()
        try:
            self._establish_settings()
            self._stack.enter_context(self._connection.transaction(force_rollback=True))
            self._verification = self._verify_settings()
            self._state = SessionState.READY
            return self
        except SessionSafetyError:
            self._state = SessionState.FAILED
            self._close_stack()
            raise
        except (ConnectNetworkError, ConnectFailedError, PginspectInternalError):
            self._state = SessionState.FAILED
            self._close_stack()
            raise
        except psycopg.Error as exc:
            self._state = SessionState.FAILED
            mapped = _map_session_sql_error(exc)
            self._close_stack()
            raise mapped from None
        except Exception as exc:
            self._state = SessionState.FAILED
            mapped = PginspectInternalError(
                "unexpected error during session establish",
                debug_frames=build_safe_debug_frames(exc),
                driver_exception_type=type(exc).__name__,
            )
            self._close_stack()
            raise mapped from None

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any
    ) -> None:
        if self._state is not SessionState.CLOSED:
            if (
                self._state is SessionState.READY
                and exc_type is not None
                and issubclass(exc_type, psycopg.Error)
            ):
                self._state = SessionState.FAILED
            self._close_stack()
            self._state = SessionState.CLOSED
        return None

    def _close_stack(self) -> None:
        stack = self._stack
        self._stack = None
        if stack is not None:
            try:
                stack.close()
            except Exception:
                pass

    def _establish_settings(self) -> None:
        expected = _expected_state(self._config)
        params = (
            f"{self._config.statement_timeout_ms}ms",
            f"{self._config.lock_timeout_ms}ms",
            f"{self._config.idle_in_transaction_session_timeout_ms}ms",
        )
        try:
            with self._connection.cursor() as cur:
                cur.execute(_ESTABLISH_SQL, params)
                cur.fetchone()
        except psycopg.Error as exc:
            sqlstate = getattr(exc, "sqlstate", None)
            sqlstate_str = sqlstate if isinstance(sqlstate, str) else None
            # Transport / cancel → operational; other server rejections → set_rejected.
            if sqlstate_str and (sqlstate_str.startswith("08") or sqlstate_str == "57014"):
                mapped = _map_session_sql_error(exc)
                raise mapped from None
            if isinstance(exc, psycopg.OperationalError) and not sqlstate_str:
                mapped = _map_session_sql_error(exc)
                raise mapped from None
            raise SessionSafetyError(
                category=SessionSafetyMisconfigurationCategory.SET_REJECTED,
                expected=expected,
                observed=None,
                sqlstate=sqlstate_str,
                debug_frames=build_safe_debug_frames(exc),
            ) from None

    def _verify_settings(self) -> SessionSafetyVerifiedEvidence:
        expected = _expected_state(self._config)
        try:
            with self._connection.cursor(row_factory=dict_row) as cur:
                cur.execute(_VERIFY_SQL)
                row = cur.fetchone()
        except psycopg.Error as exc:
            mapped = _map_session_sql_error(exc)
            raise mapped from None

        if row is None:
            raise PginspectInternalError("verification query returned no row")

        try:
            default_ro = bool(row["default_transaction_read_only"])
            txn_ro = bool(row["transaction_read_only"])
            statement_ms = int(row["statement_timeout_ms"])
            statement_unit = row["statement_timeout_unit"]
            lock_ms = int(row["lock_timeout_ms"])
            lock_unit = row["lock_timeout_unit"]
            idle_ms = int(row["idle_in_transaction_session_timeout_ms"])
            idle_unit = row["idle_in_transaction_session_timeout_unit"]
            application_name = str(row["application_name"] or "")
            search_path_raw = str(row["search_path_raw"] or "")
            effective = row["effective_search_path"]
        except (KeyError, TypeError, ValueError) as exc:
            raise PginspectInternalError(
                "verification query returned unexpected shape",
                debug_frames=build_safe_debug_frames(exc),
            ) from None

        if isinstance(effective, (list, tuple)):
            effective_path = tuple(str(x) for x in effective)
        else:
            raise PginspectInternalError("effective_search_path has unexpected type")

        observed = SessionSafetyObservedState(
            default_transaction_read_only=default_ro,
            transaction_read_only=txn_ro,
            statement_timeout_ms=statement_ms,
            lock_timeout_ms=lock_ms,
            idle_in_transaction_session_timeout_ms=idle_ms,
            search_path=effective_path,
        )

        units_ok = statement_unit == "ms" and lock_unit == "ms" and idle_unit == "ms"
        matches = (
            default_ro is True
            and txn_ro is True
            and statement_ms == expected.statement_timeout_ms
            and lock_ms == expected.lock_timeout_ms
            and idle_ms == expected.idle_in_transaction_session_timeout_ms
            and search_path_raw == "pg_catalog"
            and effective_path == ("pg_catalog",)
            and units_ok
        )
        if not matches:
            raise SessionSafetyError(
                category=SessionSafetyMisconfigurationCategory.VERIFICATION_MISMATCH,
                expected=expected,
                observed=observed,
                sqlstate=None,
            )

        app_kind, app_value = _classify_application_name(application_name)
        return SessionSafetyVerifiedEvidence(
            default_transaction_read_only=True,
            transaction_read_only=True,
            statement_timeout_ms=statement_ms,
            lock_timeout_ms=lock_ms,
            idle_in_transaction_session_timeout_ms=idle_ms,
            search_path=("pg_catalog",),
            application_name_kind=app_kind,  # type: ignore[arg-type]
            application_name_value=app_value,
            write_probe="not_run",
            verification_level="settings",
            read_only_scope="postgresql_transaction",
            read_only_is_sandbox=False,
        )

    def _ensure_ready(self) -> None:
        if self._state is SessionState.FAILED:
            raise PginspectInternalError("DiagnosticSession is FAILED and rejects further queries")
        if self._state is SessionState.CLOSED:
            raise PginspectInternalError("DiagnosticSession is CLOSED and rejects further queries")
        if self._state is not SessionState.READY:
            raise PginspectInternalError("DiagnosticSession query before READY")

    def _fetch_one(
        self,
        query: LiteralString,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> Mapping[str, object]:
        self._ensure_ready()
        try:
            with self._connection.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                row = cur.fetchone()
        except psycopg.Error as exc:
            self._state = SessionState.FAILED
            mapped = _map_session_sql_error(exc)
            raise mapped from None
        if row is None:
            raise PginspectInternalError("query returned no row")
        return row

    def _fetch_all(
        self,
        query: LiteralString,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> Sequence[Mapping[str, object]]:
        self._ensure_ready()
        try:
            with self._connection.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        except psycopg.Error as exc:
            self._state = SessionState.FAILED
            mapped = _map_session_sql_error(exc)
            raise mapped from None
        return rows

    def _execute_allowlisted_query(
        self,
        spec: QuerySpec,
        params: tuple[Any, ...],
        *,
        fetch: FetchMode = "one",
    ) -> Any:
        """Run one registry `QuerySpec` against a cursor; SQL text is never a parameter.

        This is the only place impact SQL reaches psycopg. Allowlist lookup,
        parameter validation and row decoding all live in
        `pginspect.impact.query_exec.execute_allowlisted`, which is the sole
        sanctioned caller of this method.
        """
        if self._state not in (SessionState.ESTABLISHING, SessionState.READY):
            raise PginspectInternalError(
                f"DiagnosticSession rejects allowlisted queries in state {self._state.value}"
            )
        try:
            if fetch == "none" or spec.command_kind != "SELECT":
                with self._connection.cursor() as cur:
                    cur.execute(spec.sql, params)
                return None
            with self._connection.cursor(row_factory=dict_row) as cur:
                cur.execute(spec.sql, params)
                if fetch == "all":
                    return cur.fetchall()
                return cur.fetchone()
        except psycopg.Error as exc:
            self._state = SessionState.FAILED
            raise _map_session_sql_error(exc) from None

    def as_query_executor(self, *, recorder: QueryRecorder | None = None) -> SessionQueryExecutor:
        """Production `QueryExecutor` for `resolve.py` / `catalog.py`.

        Returns the adapter that routes every catalog/resolution read through
        `execute_allowlisted` and this session's cursor, so no caller can reach
        the database without going through the registry allowlist.
        """
        return SessionQueryExecutor(session=self, recorder=recorder)

    def _run_impact_query(
        self,
        query_id: str,
        params: tuple[Any, ...],
        recorder: ImpactQueryRecorder | None,
        *,
        fetch: FetchMode = "one",
    ) -> Any:
        return execute_allowlisted(
            self,
            query_id,
            params,
            recorder=_adapt_impact_recorder(recorder),
            fetch=fetch,
        )

    def establish_impact_profile(
        self,
        *,
        recorder: ImpactQueryRecorder | None = None,
    ) -> ImpactSessionState:
        """Establish the READ ONLY REPEATABLE READ impact analysis profile.

        Normative timeline (plan Task 4 / design section 2), by query_id:

        1. ``impact.begin_read_only_rr`` — BEGIN, before any SELECT.
        2. ``catalog_snapshot_at`` stamped immediately before the first SELECT.
        3. ``impact.set_timeouts`` — first SELECT; local timeouts via
           ``set_config(..., true)`` with bound string parameters only.
        4. ``impact.capture_resolution_context`` — pre-harden path/schemas.
        5. ``impact.harden_search_path`` — ``SET LOCAL search_path = pg_catalog``.
        6. ``impact.verify_safety`` — RO scope, isolation, effective
           search_path and timeouts must match the hardened expectation; any
           mismatch raises ``SessionSafetyError`` and step 7 never runs.
        7. ``impact.preflight_reads`` — version/GUC/encoding/isolation/keywords.

        This is a distinct profile from the connect-test establish/verify
        path (`_ESTABLISH_SQL` / `_VERIFY_SQL`), which is unaffected by this
        method. A `DiagnosticSession` used for `establish_impact_profile`
        must not also be entered via `__enter__`.
        """
        if self._entered or self._state is not SessionState.NEW:
            raise PginspectInternalError(
                "establish_impact_profile cannot be called twice or reused"
            )
        self._entered = True
        self._state = SessionState.ESTABLISHING
        try:
            self._run_impact_query("impact.begin_read_only_rr", (), recorder, fetch="none")

            catalog_snapshot_at = datetime.now(UTC)

            timeout_params = (
                f"{self._config.statement_timeout_ms}ms",
                f"{self._config.lock_timeout_ms}ms",
                f"{self._config.idle_in_transaction_session_timeout_ms}ms",
            )
            self._run_impact_query("impact.set_timeouts", timeout_params, recorder, fetch="none")

            resolution_row: ResolutionCaptureRow | None = self._run_impact_query(
                "impact.capture_resolution_context", (), recorder
            )

            self._run_impact_query("impact.harden_search_path", (), recorder, fetch="none")

            verify_row: SafetyVerifyRow | None = self._run_impact_query(
                "impact.verify_safety", (), recorder
            )
            if verify_row is None:
                raise PginspectInternalError("impact safety verification returned no row")
            _verify_impact_safety_row(verify_row, self._config)

            preflight_row: PreflightRow | None = self._run_impact_query(
                "impact.preflight_reads", (), recorder
            )
        except SessionSafetyError:
            self._state = SessionState.FAILED
            raise
        except (ConnectNetworkError, ConnectFailedError, PginspectInternalError):
            self._state = SessionState.FAILED
            raise
        except psycopg.Error as exc:
            self._state = SessionState.FAILED
            mapped = _map_session_sql_error(exc)
            raise mapped from None
        except Exception as exc:
            self._state = SessionState.FAILED
            mapped = PginspectInternalError(
                "unexpected error during impact profile establish",
                debug_frames=build_safe_debug_frames(exc),
                driver_exception_type=type(exc).__name__,
            )
            raise mapped from None

        if resolution_row is None or preflight_row is None:
            self._state = SessionState.FAILED
            raise PginspectInternalError("impact profile query returned no row")

        resolution_context = _build_resolution_context(resolution_row, preflight_row)
        connection_context = _build_impact_connection_context(resolution_row, preflight_row)
        self._state = SessionState.READY

        return ImpactSessionState(
            resolution_context=resolution_context,
            connection_context=connection_context,
            catalog_snapshot_at=catalog_snapshot_at,
        )
