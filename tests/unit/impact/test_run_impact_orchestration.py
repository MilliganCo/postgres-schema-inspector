"""Orchestration tests for `run_impact` (plan Task 10)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.exceptions import (
    ConnectFailedError,
    PginspectInternalError,
    SessionSafetyError,
)
from pginspect.impact.analysis_unit import AnalysisUnit
from pginspect.impact.input import LocalPhaseError
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ExecutionPrediction,
    NoOpReason,
    Outcome,
    Risk,
)
from pginspect.impact.models.result import ImpactConnectionContext
from pginspect.impact.parse_local import LocalParsedScript, LocalStatement
from pginspect.impact.parser.ast import (
    Identifier,
    QualifiedName,
    SourceSpan,
    SupportedAlterDrop,
    Token,
    TokenKind,
)
from pginspect.impact.preflight import PreflightEvaluation, PreflightGateFailure, ResolutionContext
from pginspect.impact.resolve import RelationResolution
from pginspect.impact.run import EarlyOutcomeKind, EarlySemanticOutcome, run_impact
from pginspect.impact.sequence import SEQUENCE_DEPENDENCY_LIMITATION
from pginspect.models.enums import (
    ClassificationSource,
    ExecutionErrorCode,
    SessionSafetyMisconfigurationCategory,
)
from pginspect.models.finding import SessionSafetyExpectedState
from pginspect.session import ImpactSessionState


def _tok(word: str) -> Token:
    return Token(TokenKind.WORD, word, word.lower(), SourceSpan(1, 1, 0, len(word)))


def _ident(name: str, *, quoted: bool = False) -> Identifier:
    raw = _tok(name)
    return Identifier(
        raw_token_private=raw,
        value=name,
        quoted=quoted,
        normalized_value=name if quoted else name.lower(),
        source_span=raw.span,
    )


def _qn(schema: str | None, name: str) -> QualifiedName:
    return QualifiedName(
        schema=_ident(schema) if schema else None,
        name=_ident(name),
        normalized=f"{schema}.{name}" if schema else name,
    )


def _local_stmt(
    index: int,
    preview: str = "ALTER TABLE t DROP COLUMN c",
    *,
    control: bool = False,
) -> LocalStatement:
    return LocalStatement(
        statement_index=index,
        is_control=control,
        start_line=index,
        end_line=index,
        tokens=(_tok("ALTER"),),
        statement_fingerprint=f"sha256:{index:016x}",
        sanitized_preview=preview,
    )


def _script(*stmts: LocalStatement) -> LocalParsedScript:
    return LocalParsedScript(
        path_basename="migration.sql",
        statements=stmts,
        control_ordinals=tuple(s.statement_index for s in stmts if s.is_control),
        source_statement_count=len(stmts),
    )


def _resolution_context() -> ResolutionContext:
    return ResolutionContext(
        database="db",
        role="role",
        session_user="role",
        current_schema="public",
        current_schemas_user=("public",),
        current_schemas_with_implicit=("pg_catalog", "public"),
        search_path_raw='"public"',
        max_identifier_length_bytes=63,
        server_major=16,
        server_version_num=160000,
        keyword_categories={},
    )


def _connection_context(**overrides: Any) -> ImpactConnectionContext:
    base = dict(
        server_version="16.0",
        server_version_num=160000,
        server_major=16,
        database="db",
        role="role",
        session_user="role",
        current_schema="public",
        search_path_raw='"public"',
        standard_conforming_strings="on",
        server_encoding="UTF8",
        client_encoding="UTF8",
        transaction_isolation="repeatable read",
        transaction_read_only="on",
        in_recovery=False,
        max_identifier_length=63,
    )
    base.update(overrides)
    return ImpactConnectionContext(**base)


def _profile(ctx: ImpactConnectionContext | None = None) -> ImpactSessionState:
    connection = ctx or _connection_context()
    return ImpactSessionState(
        resolution_context=_resolution_context(),
        connection_context=connection,
        catalog_snapshot_at=datetime(2026, 7, 30, tzinfo=UTC),
    )


@dataclass
class _FakeConn:
    rollbacks: list[str]

    def rollback(self) -> None:
        self.rollbacks.append("rollback")


@pytest.fixture
def configs() -> tuple[ConnectionConfig, SessionSafetyConfig]:
    return ConnectionConfig(host="localhost"), SessionSafetyConfig()


def test_malformed_local_opens_no_connection(
    configs: tuple[ConnectionConfig, SessionSafetyConfig],
) -> None:
    conn_cfg, safety = configs
    with (
        patch("pginspect.impact.run.parse_migration_path", side_effect=LocalPhaseError("bad")),
        patch("pginspect.impact.run.open_connection") as open_conn,
    ):
        with pytest.raises(LocalPhaseError, match="bad"):
            run_impact(Path("x.sql"), conn_cfg, safety)
    open_conn.assert_not_called()


def test_pipeline_stage_order(configs: tuple[ConnectionConfig, SessionSafetyConfig]) -> None:
    conn_cfg, safety = configs
    order: list[str] = []
    fake_conn = _FakeConn([])

    class _CM:
        def __enter__(self) -> _FakeConn:
            order.append("open_connection")
            return fake_conn

        def __exit__(self, *args: object) -> None:
            return None

    drop_ast = SupportedAlterDrop(
        table=__import__("pginspect.impact.parser.ast", fromlist=["TableRef"]).TableRef(
            if_exists=True, qualified_name=_qn("public", "t")
        ),
        column=_ident("c"),
        if_exists=True,
        drop_behavior_written="default",
        effective_behavior="restrict",
    )

    unit = AnalysisUnit(
        statement_index=1,
        source_span=SourceSpan(1, 1, 0, 10),
        statement_fingerprint="sha256:0000000000000001",
        sanitized_preview="ALTER TABLE public.t DROP COLUMN c",
        family="drop",
        ast=drop_ast,
        analysis_status=AnalysisStatus.ANALYZED,
        table_oid=None,
        table_schema="public",
        table_name="t",
        column_attnum=None,
        column_normalized_name="c",
        resolution_payload=EarlySemanticOutcome(EarlyOutcomeKind.TARGET_MISSING_IF_EXISTS),
        evidence_ids=(),
        requires_virtual_schema_state=False,
        limitations=(),
    )

    def _build(*args: Any, **kwargs: Any) -> AnalysisUnit:
        order.append("build_unit")
        return unit

    def _seq(units: Any) -> tuple[AnalysisUnit, ...]:
        order.append("sequence")
        return tuple(units)

    session = MagicMock()
    session.establish_impact_profile.side_effect = lambda **kwargs: (
        order.append("establish_impact_profile") or _profile()
    )
    session.as_query_executor.side_effect = lambda **kwargs: (
        order.append("executor") or MagicMock()
    )
    session.force_rollback.side_effect = lambda: order.append("rollback")

    with (
        patch("pginspect.impact.run.parse_migration_path", return_value=_script(_local_stmt(1))),
        patch("pginspect.impact.run.open_connection", return_value=_CM()),
        patch("pginspect.impact.run.DiagnosticSession", return_value=session),
        patch(
            "pginspect.impact.run.evaluate_preflight_gates",
            return_value=PreflightEvaluation(False, ()),
        ),
        patch("pginspect.impact.run._build_unit_for_statement", side_effect=_build),
        patch("pginspect.impact.run.apply_sequence_constraints", side_effect=_seq),
    ):
        result = run_impact(Path("migration.sql"), conn_cfg, safety)

    assert order == [
        "open_connection",
        "establish_impact_profile",
        "executor",
        "build_unit",
        "sequence",
        "rollback",
    ]
    assert result.outcome is Outcome.COMPLETED
    assert result.statements[0].no_op_reason is NoOpReason.TARGET_MISSING_IF_EXISTS


@pytest.mark.parametrize(
    ("if_exists", "prediction", "reason", "risk", "exit_code"),
    [
        (True, ExecutionPrediction.NO_OP, NoOpReason.TARGET_MISSING_IF_EXISTS, Risk.SAFE, 0),
        (False, ExecutionPrediction.WOULD_FAIL, None, Risk.CRITICAL, 2),
    ],
)
def test_missing_table_matrix(
    configs: tuple[ConnectionConfig, SessionSafetyConfig],
    if_exists: bool,
    prediction: ExecutionPrediction,
    reason: NoOpReason | None,
    risk: Risk,
    exit_code: int,
) -> None:
    conn_cfg, safety = configs
    from pginspect.impact.parser.ast import TableRef

    ast = SupportedAlterDrop(
        table=TableRef(if_exists=if_exists, qualified_name=_qn("public", "missing")),
        column=_ident("c"),
        if_exists=False,
        drop_behavior_written="default",
        effective_behavior="restrict",
    )
    fake_conn = _FakeConn([])

    class _CM:
        def __enter__(self) -> _FakeConn:
            return fake_conn

        def __exit__(self, *args: object) -> None:
            return None

    session = MagicMock()
    session.establish_impact_profile.return_value = _profile()
    session.as_query_executor.return_value = MagicMock()

    with (
        patch("pginspect.impact.run.parse_migration_path", return_value=_script(_local_stmt(1))),
        patch("pginspect.impact.run.open_connection", return_value=_CM()),
        patch("pginspect.impact.run.DiagnosticSession", return_value=session),
        patch(
            "pginspect.impact.run.evaluate_preflight_gates",
            return_value=PreflightEvaluation(False, ()),
        ),
        patch(
            "pginspect.impact.run.classify_noncontrol_statement",
            return_value=ast,
        ),
        patch(
            "pginspect.impact.run.resolve_relation",
            return_value=RelationResolution("not_found", None, None, None, None),
        ),
        patch("pginspect.impact.run.evaluate_drop_column") as drop_rule,
        patch("pginspect.impact.run.evaluate_type_change") as type_rule,
        patch("pginspect.impact.run.evaluate_add_column") as add_rule,
    ):
        result = run_impact(Path("migration.sql"), conn_cfg, safety)

    assert result.statements[0].execution_prediction is prediction
    assert result.statements[0].no_op_reason is reason
    assert result.statements[0].risk is risk
    assert result.statements[0].analysis_status is AnalysisStatus.ANALYZED
    assert result.exit_code == exit_code
    drop_rule.assert_not_called()
    type_rule.assert_not_called()
    add_rule.assert_not_called()


@pytest.mark.parametrize(
    ("col_if_exists", "prediction", "reason", "risk", "exit_code"),
    [
        (True, ExecutionPrediction.NO_OP, NoOpReason.COLUMN_MISSING_IF_EXISTS, Risk.SAFE, 0),
        (False, ExecutionPrediction.WOULD_FAIL, None, Risk.CRITICAL, 2),
    ],
)
def test_missing_column_matrix(
    configs: tuple[ConnectionConfig, SessionSafetyConfig],
    col_if_exists: bool,
    prediction: ExecutionPrediction,
    reason: NoOpReason | None,
    risk: Risk,
    exit_code: int,
) -> None:
    conn_cfg, safety = configs
    from pginspect.impact.parser.ast import TableRef
    from pginspect.impact.models.catalog_types import RelationSnapshot

    ast = SupportedAlterDrop(
        table=TableRef(if_exists=False, qualified_name=_qn("public", "t")),
        column=_ident("missing_col"),
        if_exists=col_if_exists,
        drop_behavior_written="default",
        effective_behavior="restrict",
    )
    relation = RelationSnapshot(
        oid=10,
        nspname="public",
        relname="t",
        relkind="r",
        relpersistence="p",
        relispartition=False,
        inherits_parents=(),
        inherits_children=(),
        columns=(),
        indexes=(),
        constraints=(),
    )
    fake_conn = _FakeConn([])

    class _CM:
        def __enter__(self) -> _FakeConn:
            return fake_conn

        def __exit__(self, *args: object) -> None:
            return None

    session = MagicMock()
    session.establish_impact_profile.return_value = _profile()
    session.as_query_executor.return_value = MagicMock()

    with (
        patch("pginspect.impact.run.parse_migration_path", return_value=_script(_local_stmt(1))),
        patch("pginspect.impact.run.open_connection", return_value=_CM()),
        patch("pginspect.impact.run.DiagnosticSession", return_value=session),
        patch(
            "pginspect.impact.run.evaluate_preflight_gates",
            return_value=PreflightEvaluation(False, ()),
        ),
        patch("pginspect.impact.run.classify_noncontrol_statement", return_value=ast),
        patch(
            "pginspect.impact.run.resolve_relation",
            return_value=RelationResolution("resolved", 10, "public", "t", None),
        ),
        patch("pginspect.impact.run.fetch_relation_snapshot", return_value=relation),
        patch("pginspect.impact.run.evaluate_drop_column") as drop_rule,
        patch("pginspect.impact.run.evaluate_type_change") as type_rule,
        patch("pginspect.impact.run.evaluate_add_column") as add_rule,
    ):
        result = run_impact(Path("migration.sql"), conn_cfg, safety)

    assert result.statements[0].execution_prediction is prediction
    assert result.statements[0].no_op_reason is reason
    assert result.statements[0].risk is risk
    assert result.exit_code == exit_code
    drop_rule.assert_not_called()
    type_rule.assert_not_called()
    add_rule.assert_not_called()


def test_noop_cards_do_not_raise_exit_in_mixed_script(
    configs: tuple[ConnectionConfig, SessionSafetyConfig],
) -> None:
    """Proven IF EXISTS no-ops contribute exit 0 and do not raise a mixed script."""
    conn_cfg, safety = configs
    from pginspect.impact.parser.ast import TableRef

    missing_table = SupportedAlterDrop(
        table=TableRef(if_exists=True, qualified_name=_qn("public", "missing")),
        column=_ident("c"),
        if_exists=False,
        drop_behavior_written="default",
        effective_behavior="restrict",
    )
    missing_column = SupportedAlterDrop(
        table=TableRef(if_exists=False, qualified_name=_qn("public", "t")),
        column=_ident("gone"),
        if_exists=True,
        drop_behavior_written="default",
        effective_behavior="restrict",
    )
    relation = __import__(
        "pginspect.impact.models.catalog_types", fromlist=["RelationSnapshot"]
    ).RelationSnapshot(
        oid=10,
        nspname="public",
        relname="t",
        relkind="r",
        relpersistence="p",
        relispartition=False,
        inherits_parents=(),
        inherits_children=(),
        columns=(),
        indexes=(),
        constraints=(),
    )
    fake_conn = _FakeConn([])

    class _CM:
        def __enter__(self) -> _FakeConn:
            return fake_conn

        def __exit__(self, *args: object) -> None:
            return None

    session = MagicMock()
    session.establish_impact_profile.return_value = _profile()
    session.as_query_executor.return_value = MagicMock()
    classifications = iter([missing_table, missing_column])
    resolutions = iter(
        [
            RelationResolution("not_found", None, None, None, None),
            RelationResolution("resolved", 10, "public", "t", None),
        ]
    )

    with (
        patch(
            "pginspect.impact.run.parse_migration_path",
            return_value=_script(_local_stmt(1), _local_stmt(2)),
        ),
        patch("pginspect.impact.run.open_connection", return_value=_CM()),
        patch("pginspect.impact.run.DiagnosticSession", return_value=session),
        patch(
            "pginspect.impact.run.evaluate_preflight_gates",
            return_value=PreflightEvaluation(False, ()),
        ),
        patch(
            "pginspect.impact.run.classify_noncontrol_statement",
            side_effect=lambda *a, **k: next(classifications),
        ),
        patch(
            "pginspect.impact.run.resolve_relation",
            side_effect=lambda **k: next(resolutions),
        ),
        patch("pginspect.impact.run.fetch_relation_snapshot", return_value=relation),
    ):
        result = run_impact(Path("migration.sql"), conn_cfg, safety)

    assert result.outcome is Outcome.COMPLETED
    assert result.exit_code == 0
    assert {c.risk for c in result.statements} == {Risk.SAFE}
    assert all(c.execution_prediction is ExecutionPrediction.NO_OP for c in result.statements)


def test_preflight_incomplete_empty_statements(
    configs: tuple[ConnectionConfig, SessionSafetyConfig],
) -> None:
    conn_cfg, safety = configs
    rollbacks: list[str] = []
    fake_conn = _FakeConn(rollbacks)

    class _CM:
        def __enter__(self) -> _FakeConn:
            return fake_conn

        def __exit__(self, *args: object) -> None:
            return None

    session = MagicMock()
    session.establish_impact_profile.return_value = _profile(
        _connection_context(server_major=10, server_version_num=100000)
    )
    session.force_rollback.side_effect = lambda: rollbacks.append("rb")

    with (
        patch("pginspect.impact.run.parse_migration_path", return_value=_script(_local_stmt(1))),
        patch("pginspect.impact.run.open_connection", return_value=_CM()),
        patch("pginspect.impact.run.DiagnosticSession", return_value=session),
        patch(
            "pginspect.impact.run.evaluate_preflight_gates",
            return_value=PreflightEvaluation(
                True, (PreflightGateFailure("server_major", "unsupported"),)
            ),
        ),
    ):
        result = run_impact(Path("migration.sql"), conn_cfg, safety)

    assert result.outcome is Outcome.INCOMPLETE
    assert result.exit_code == 3
    assert result.statements == ()
    assert result.summary.incomplete is True
    assert rollbacks == ["rb"]
    session.force_rollback.assert_called()


@pytest.mark.parametrize(
    ("fail_at", "exc"),
    [
        (
            "profile",
            SessionSafetyError(
                category=SessionSafetyMisconfigurationCategory.VERIFICATION_MISMATCH,
                expected=SessionSafetyExpectedState(
                    default_transaction_read_only=True,
                    transaction_read_only=True,
                    statement_timeout_ms=1,
                    lock_timeout_ms=1,
                    idle_in_transaction_session_timeout_ms=1,
                    search_path=("pg_catalog",),
                ),
                observed=None,
            ),
        ),
        ("catalog", PginspectInternalError("catalog boom")),
        ("rule", PginspectInternalError("rule boom")),
        ("success", None),
    ],
)
def test_rollback_on_db_paths(
    configs: tuple[ConnectionConfig, SessionSafetyConfig],
    fail_at: str,
    exc: Exception | None,
) -> None:
    conn_cfg, safety = configs
    rollbacks: list[str] = []
    fake_conn = _FakeConn([])

    class _CM:
        def __enter__(self) -> _FakeConn:
            return fake_conn

        def __exit__(self, *args: object) -> None:
            return None

    session = MagicMock()
    session.force_rollback.side_effect = lambda: rollbacks.append("rb")
    if fail_at == "profile":
        session.establish_impact_profile.side_effect = exc
    else:
        session.establish_impact_profile.return_value = _profile()
        session.as_query_executor.return_value = MagicMock()

    from pginspect.impact.parser.ast import TableRef

    ast = SupportedAlterDrop(
        table=TableRef(if_exists=True, qualified_name=_qn("public", "t")),
        column=_ident("c"),
        if_exists=True,
        drop_behavior_written="default",
        effective_behavior="restrict",
    )

    patches: list[Any] = [
        patch("pginspect.impact.run.parse_migration_path", return_value=_script(_local_stmt(1))),
        patch("pginspect.impact.run.open_connection", return_value=_CM()),
        patch("pginspect.impact.run.DiagnosticSession", return_value=session),
    ]
    if fail_at != "profile":
        patches.extend(
            [
                patch(
                    "pginspect.impact.run.evaluate_preflight_gates",
                    return_value=PreflightEvaluation(False, ()),
                ),
                patch("pginspect.impact.run.classify_noncontrol_statement", return_value=ast),
            ]
        )
        if fail_at == "catalog":
            patches.append(
                patch("pginspect.impact.run.resolve_relation", side_effect=exc),
            )
        elif fail_at == "rule":
            patches.extend(
                [
                    patch(
                        "pginspect.impact.run.resolve_relation",
                        return_value=RelationResolution("found", 42, "public", "t", "basetable"),
                    ),
                    patch(
                        "pginspect.impact.run._build_unit_for_statement",
                        side_effect=exc,
                    ),
                ]
            )
        else:
            patches.extend(
                [
                    patch(
                        "pginspect.impact.run.resolve_relation",
                        return_value=RelationResolution("not_found", None, None, None, None),
                    ),
                ]
            )

    with patches[0], patches[1], patches[2]:
        if fail_at == "profile":
            result = run_impact(Path("migration.sql"), conn_cfg, safety)
            assert result.outcome is Outcome.FAILED
            assert result.exit_code == 3
        elif fail_at in {"catalog", "rule"}:
            with patches[3], patches[4], patches[5]:
                if fail_at == "rule":
                    with patches[6]:
                        result = run_impact(Path("migration.sql"), conn_cfg, safety)
                else:
                    result = run_impact(Path("migration.sql"), conn_cfg, safety)
            assert result.outcome is Outcome.FAILED
            assert result.exit_code == 5
        else:
            with patches[3], patches[4], patches[5]:
                result = run_impact(Path("migration.sql"), conn_cfg, safety)
            assert result.outcome is Outcome.COMPLETED

    assert rollbacks == ["rb"]
    session.force_rollback.assert_called()


def test_unsupported_sequence_preserved(
    configs: tuple[ConnectionConfig, SessionSafetyConfig],
) -> None:
    conn_cfg, safety = configs
    fake_conn = _FakeConn([])

    class _CM:
        def __enter__(self) -> _FakeConn:
            return fake_conn

        def __exit__(self, *args: object) -> None:
            return None

    u1 = AnalysisUnit(
        statement_index=1,
        source_span=SourceSpan(1, 1, 0, 10),
        statement_fingerprint="sha256:0000000000000001",
        sanitized_preview="ADD",
        family="add",
        ast=object(),
        analysis_status=AnalysisStatus.ANALYZED,
        table_oid=10,
        table_schema="public",
        table_name="t",
        column_attnum=None,
        column_normalized_name="x",
        resolution_payload=EarlySemanticOutcome(EarlyOutcomeKind.TARGET_MISSING_IF_EXISTS),
        evidence_ids=(),
        requires_virtual_schema_state=True,
        limitations=(),
    )
    u2 = AnalysisUnit(
        statement_index=2,
        source_span=SourceSpan(2, 2, 0, 10),
        statement_fingerprint="sha256:0000000000000002",
        sanitized_preview="TYPE",
        family="type",
        ast=object(),
        analysis_status=AnalysisStatus.ANALYZED,
        table_oid=10,
        table_schema="public",
        table_name="t",
        column_attnum=None,
        column_normalized_name="x",
        resolution_payload=EarlySemanticOutcome(EarlyOutcomeKind.TARGET_MISSING_IF_EXISTS),
        evidence_ids=(),
        requires_virtual_schema_state=False,
        limitations=(),
    )
    sequenced = (
        u1,
        AnalysisUnit(
            statement_index=2,
            source_span=u2.source_span,
            statement_fingerprint=u2.statement_fingerprint,
            sanitized_preview=u2.sanitized_preview,
            family="type",
            ast=u2.ast,
            analysis_status=AnalysisStatus.UNSUPPORTED_SEQUENCE,
            table_oid=10,
            table_schema="public",
            table_name="t",
            column_attnum=None,
            column_normalized_name="x",
            resolution_payload=u2.resolution_payload,
            evidence_ids=(),
            requires_virtual_schema_state=False,
            limitations=(SEQUENCE_DEPENDENCY_LIMITATION,),
        ),
    )

    session = MagicMock()
    session.establish_impact_profile.return_value = _profile()
    session.as_query_executor.return_value = MagicMock()
    builds = iter([u1, u2])

    with (
        patch(
            "pginspect.impact.run.parse_migration_path",
            return_value=_script(_local_stmt(1, "ADD"), _local_stmt(2, "TYPE")),
        ),
        patch("pginspect.impact.run.open_connection", return_value=_CM()),
        patch("pginspect.impact.run.DiagnosticSession", return_value=session),
        patch(
            "pginspect.impact.run.evaluate_preflight_gates",
            return_value=PreflightEvaluation(False, ()),
        ),
        patch(
            "pginspect.impact.run._build_unit_for_statement",
            side_effect=lambda *a, **k: next(builds),
        ),
        patch("pginspect.impact.run.apply_sequence_constraints", return_value=sequenced),
        patch("pginspect.impact.run.evaluate_type_change") as type_rule,
    ):
        result = run_impact(Path("migration.sql"), conn_cfg, safety)

    assert result.statements[0].statement_index == 1
    assert result.statements[1].statement_index == 2
    assert result.statements[1].analysis_status is AnalysisStatus.UNSUPPORTED_SEQUENCE
    assert result.statements[1].execution_prediction is ExecutionPrediction.NOT_EVALUATED
    assert result.outcome is Outcome.INCOMPLETE
    assert result.exit_code == 3
    type_rule.assert_not_called()


def test_connect_failure_exit_3(configs: tuple[ConnectionConfig, SessionSafetyConfig]) -> None:
    conn_cfg, safety = configs
    with (
        patch("pginspect.impact.run.parse_migration_path", return_value=_script(_local_stmt(1))),
        patch(
            "pginspect.impact.run.open_connection",
            side_effect=ConnectFailedError(
                code=ExecutionErrorCode.CONNECTION_FAILED,
                classification_source=ClassificationSource.FALLBACK_OTHER,
            ),
        ),
    ):
        result = run_impact(Path("migration.sql"), conn_cfg, safety)
    assert result.outcome is Outcome.FAILED
    assert result.exit_code == 3
    assert result.error is not None
    assert result.statements == ()
