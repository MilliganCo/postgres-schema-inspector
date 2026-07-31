"""Output-agnostic `run_impact` orchestration (plan Task 10).

Pipeline (design section 0 / plan Task 10):

```text
local parse
→ connect
→ establish impact profile
→ classify
→ resolve
→ catalog evidence
→ sequence constraints
→ family rules / early semantic outcomes
→ evidence/card/result assembly
→ force rollback
```

`LocalPhaseError` propagates without producing a result (CLI exit 4).
Every path that opens a connection rolls it back before returning.
Missing qualified targets and missing columns are decided here *before*
rule engines so DROP's defensive `unsupported_evidence` fallback is never
used for proven absence.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pginspect._version import get_app_version
from pginspect.config import ConnectionConfig, SessionSafetyConfig
from pginspect.connection import open_connection
from pginspect.error_catalog import public_connect_message, retryable_for
from pginspect.exceptions import (
    PginspectConnectError,
    PginspectInternalError,
    SessionSafetyError,
)
from pginspect.impact.analysis_unit import AnalysisUnit
from pginspect.impact.catalog import (
    fetch_pg_cast_rows,
    fetch_relation_metrics,
    fetch_relation_snapshot,
    fetch_type_snapshot,
    gather_dependency_edges,
)
from pginspect.impact.models.card import ImpactConfidence, ImpactStatementCard
from pginspect.impact.models.catalog_types import (
    ColumnSnapshot,
    RelationSnapshot,
    TypeSnapshot,
)
from pginspect.impact.models.enums import (
    AnalysisStage,
    AnalysisStatus,
    ConfidenceLevel,
    EvidenceKind,
    ExecutionPrediction,
    ImpactPreflightCheckStatus,
    ImpactScaleConfidence,
    LockMode,
    NoOpReason,
    Outcome,
    PhysicalTriState,
    PreflightStatus,
    Risk,
)
from pginspect.impact.models.evidence import ImpactEvidence
from pginspect.impact.models.result import (
    ImpactCommandResult,
    ImpactConnectionContext,
    ImpactInputMeta,
    ImpactPreflight,
    ImpactPreflightCheck,
    ImpactSnapshot,
    ImpactSummary,
)
from pginspect.impact.input import LocalPhaseError
from pginspect.impact.parse_local import LocalParsedScript, LocalStatement, parse_migration_path
from pginspect.impact.parser.ast import (
    QualifiedName,
    SourceSpan,
    SupportedAlterAdd,
    SupportedAlterDrop,
    SupportedAlterType,
    UnsupportedParserAst,
)
from pginspect.impact.parser.classify import classify_noncontrol_statement
from pginspect.impact.preflight import ResolutionContext, evaluate_preflight_gates
from pginspect.impact.resolve import resolve_relation, resolve_type
from pginspect.impact.rules.add_column import AddColumnFacts, evaluate_add_column
from pginspect.impact.rules.contracts import AUTHORIZATION_LIMITATION, RuleVerdict
from pginspect.impact.rules.drop_column import DropColumnFacts, evaluate_drop_column
from pginspect.impact.rules.severity import aggregate_exit_code
from pginspect.impact.rules.type_change import TypeChangeFacts, evaluate_type_change
from pginspect.impact.sequence import apply_sequence_constraints
from pginspect.models.enums import (
    ClassificationSource,
    ExecutionErrorCategory,
    ExecutionErrorCode,
)
from pginspect.models.execution_error import DebugPayload, ExecutionError
from pginspect.session import DiagnosticSession, ImpactSessionState

__all__ = ["run_impact", "_force_rollback"]

_NA = PhysicalTriState.NOT_APPLICABLE
_NO = PhysicalTriState.NO
_HIGH = ConfidenceLevel.HIGH
_NA_CONF = ConfidenceLevel.NOT_APPLICABLE


class EarlyOutcomeKind(StrEnum):
    TARGET_MISSING_IF_EXISTS = "target_missing_if_exists"
    TARGET_MISSING_WOULD_FAIL = "target_missing_would_fail"
    COLUMN_MISSING_IF_EXISTS = "column_missing_if_exists"
    COLUMN_MISSING_WOULD_FAIL = "column_missing_would_fail"
    COLUMN_ALREADY_EXISTS_IF_NOT_EXISTS = "column_already_exists_if_not_exists"


@dataclass(frozen=True)
class EarlySemanticOutcome:
    """Resolution-time semantic decision that must not reach a rule engine."""

    kind: EarlyOutcomeKind


@dataclass(frozen=True)
class CatalogBoundPayload:
    """Catalog facts attached to an `AnalysisUnit` for later rule evaluation."""

    family: Literal["type", "add", "drop"]
    relation: RelationSnapshot
    column: ColumnSnapshot | None
    source_type: TypeSnapshot | None
    target_type: TypeSnapshot | None
    pg_cast_rows: tuple[Any, ...]
    dependency_edges: tuple[Any, ...]
    dependency_graph_complete: bool
    truncated_at_limit: bool
    metrics_present: bool
    n_live_tup: int | None
    server_major: int
    using_present: bool
    effective_behavior: Literal["restrict", "cascade"] | None
    if_not_exists: bool
    nullability: Literal["unspecified", "null", "not_null"] | None
    has_default_tokens: bool


def _force_rollback(connection: Any) -> None:
    """Abort the impact READ ONLY transaction opened by `establish_impact_profile`."""
    connection.rollback()


def _now() -> datetime:
    return datetime.now(UTC)


def _empty_summary(*, incomplete: bool) -> ImpactSummary:
    return ImpactSummary(
        overall_risk=Risk.NOT_APPLICABLE,
        critical_count=0,
        warning_count=0,
        safe_count=0,
        not_applicable_count=0,
        would_fail_count=0,
        may_fail_count=0,
        unsupported_count=0,
        no_op_count=0,
        analyzed_count=0,
        incomplete=incomplete,
    )


def _summarize(cards: Sequence[ImpactStatementCard], *, incomplete: bool) -> ImpactSummary:
    if not cards:
        return _empty_summary(incomplete=incomplete)
    critical = warning = safe = not_applicable = 0
    would_fail = may_fail = unsupported = no_op = analyzed = 0
    for card in cards:
        if card.risk is Risk.CRITICAL:
            critical += 1
        elif card.risk is Risk.WARNING:
            warning += 1
        elif card.risk is Risk.SAFE:
            safe += 1
        else:
            not_applicable += 1
        if card.execution_prediction is ExecutionPrediction.WOULD_FAIL:
            would_fail += 1
        elif card.execution_prediction is ExecutionPrediction.MAY_FAIL:
            may_fail += 1
        if card.analysis_status.value.startswith("unsupported_"):
            unsupported += 1
        if card.execution_prediction is ExecutionPrediction.NO_OP:
            no_op += 1
        if card.analysis_status is AnalysisStatus.ANALYZED:
            analyzed += 1
    overall = max(
        (card.risk for card in cards),
        key=lambda risk: {
            Risk.NOT_APPLICABLE: 0,
            Risk.SAFE: 1,
            Risk.WARNING: 2,
            Risk.CRITICAL: 3,
        }[risk],
    )
    return ImpactSummary(
        overall_risk=overall,
        critical_count=critical,
        warning_count=warning,
        safe_count=safe,
        not_applicable_count=not_applicable,
        would_fail_count=would_fail,
        may_fail_count=may_fail,
        unsupported_count=unsupported,
        no_op_count=no_op,
        analyzed_count=analyzed,
        incomplete=incomplete,
    )


def _execution_error_from_connect(exc: PginspectConnectError) -> ExecutionError:
    return ExecutionError(
        code=exc.code,
        category=ExecutionErrorCategory.CONNECTION
        if exc.code is not ExecutionErrorCode.OPERATIONAL_FAILURE
        else ExecutionErrorCategory.OPERATIONAL,
        message=public_connect_message(exc.code),
        retryable=retryable_for(exc.code),
        sqlstate=exc.sqlstate,
        classification_source=exc.classification_source,
        debug=None,
    )


def _execution_error_session_safety(exc: SessionSafetyError) -> ExecutionError:
    return ExecutionError(
        code=ExecutionErrorCode.OPERATIONAL_FAILURE,
        category=ExecutionErrorCategory.OPERATIONAL,
        message=public_connect_message(ExecutionErrorCode.OPERATIONAL_FAILURE),
        retryable=retryable_for(ExecutionErrorCode.OPERATIONAL_FAILURE),
        sqlstate=exc.sqlstate,
        classification_source=ClassificationSource.FALLBACK_OTHER,
        debug=None,
    )


def _execution_error_internal(exc: PginspectInternalError) -> ExecutionError:
    return ExecutionError(
        code=ExecutionErrorCode.INTERNAL_FAILURE,
        category=ExecutionErrorCategory.INTERNAL,
        message=public_connect_message(ExecutionErrorCode.INTERNAL_FAILURE),
        retryable=False,
        sqlstate=None,
        classification_source=None,
        debug=DebugPayload(
            exception_type=type(exc).__name__,
            causal_chain_types=(),
            frames=(),
        )
        if exc.driver_exception_type
        else None,
    )


def _failed_result(
    *,
    script: LocalParsedScript | None,
    started_at: datetime,
    duration_ms: int,
    error: ExecutionError,
    connection_context: ImpactConnectionContext | None = None,
    stage: AnalysisStage = AnalysisStage.CONNECT,
) -> ImpactCommandResult:
    exit_code: Literal[3, 5] = 5 if error.code is ExecutionErrorCode.INTERNAL_FAILURE else 3
    input_meta = ImpactInputMeta(
        path_basename=script.path_basename if script is not None else "",
        source_statement_count=script.source_statement_count if script is not None else 0,
        card_count=0,
        control_statement_count=len(script.control_ordinals) if script is not None else 0,
    )
    return ImpactCommandResult(
        outcome=Outcome.FAILED,
        exit_code=exit_code,
        started_at=started_at,
        duration_ms=duration_ms,
        app_version=get_app_version(),
        input=input_meta,
        connection_context=connection_context,
        preflight=ImpactPreflight(
            status=PreflightStatus.FAILED,
            analysis_stage_reached=stage,
            checks=(),
            limitations=(),
        ),
        snapshot=None,
        summary=_empty_summary(incomplete=True),
        statements=(),
        evidence=(),
        error=error,
    )


def _schema_name(qualified: QualifiedName) -> str | None:
    if qualified.schema is None:
        return None
    return qualified.schema.normalized_value


def _ident_name(qualified: QualifiedName) -> str:
    if qualified.name is not None:
        return qualified.name.normalized_value
    return qualified.normalized


def _find_column(relation: RelationSnapshot, column_name: str) -> ColumnSnapshot | None:
    for column in relation.columns:
        if column.attisdropped:
            continue
        if column.attname == column_name:
            return column
    return None


def _indexes_on_column(relation: RelationSnapshot, attnum: int) -> bool:
    return any(attnum in index.indkey_attnums for index in relation.indexes)


def _na_confidence() -> ImpactConfidence:
    return ImpactConfidence(
        lock=_NA_CONF,
        rewrite=_NA_CONF,
        execution=_NA_CONF,
        dependencies=_NA_CONF,
        impact_scale=ImpactScaleConfidence.NOT_APPLICABLE,
    )


def _analyzed_confidence(*, metrics_present: bool) -> ImpactConfidence:
    return ImpactConfidence(
        lock=_HIGH,
        rewrite=_HIGH,
        execution=_HIGH,
        dependencies=_HIGH,
        impact_scale=ImpactScaleConfidence.MEDIUM if metrics_present else ImpactScaleConfidence.LOW,
    )


def _card_from_early(
    stmt: LocalStatement,
    outcome: EarlySemanticOutcome,
) -> tuple[ImpactStatementCard, tuple[ImpactEvidence, ...]]:
    if outcome.kind is EarlyOutcomeKind.TARGET_MISSING_IF_EXISTS:
        card = ImpactStatementCard(
            statement_index=stmt.statement_index,
            start_line=stmt.start_line,
            end_line=stmt.end_line,
            statement_fingerprint=stmt.statement_fingerprint,
            sanitized_preview=stmt.sanitized_preview,
            analysis_status=AnalysisStatus.ANALYZED,
            execution_prediction=ExecutionPrediction.NO_OP,
            no_op_reason=NoOpReason.TARGET_MISSING_IF_EXISTS,
            risk=Risk.SAFE,
            confidence=_na_confidence(),
            lock=LockMode.NOT_APPLICABLE,
            table_rewrite=_NA,
            table_scan=_NA,
            index_rebuild=_NA,
            limitations=(AUTHORIZATION_LIMITATION,),
            evidence_refs=(),
            why=("Target relation is missing and IF EXISTS was written.",),
        )
        return card, ()
    if outcome.kind is EarlyOutcomeKind.TARGET_MISSING_WOULD_FAIL:
        card = ImpactStatementCard(
            statement_index=stmt.statement_index,
            start_line=stmt.start_line,
            end_line=stmt.end_line,
            statement_fingerprint=stmt.statement_fingerprint,
            sanitized_preview=stmt.sanitized_preview,
            analysis_status=AnalysisStatus.ANALYZED,
            execution_prediction=ExecutionPrediction.WOULD_FAIL,
            no_op_reason=None,
            risk=Risk.CRITICAL,
            confidence=_analyzed_confidence(metrics_present=False),
            lock=LockMode.ACCESS_EXCLUSIVE_LOCK,
            table_rewrite=_NA,
            table_scan=_NA,
            index_rebuild=_NA,
            limitations=(AUTHORIZATION_LIMITATION,),
            evidence_refs=(),
            why=("Target relation is missing and IF EXISTS was not written.",),
        )
        return card, ()
    if outcome.kind is EarlyOutcomeKind.COLUMN_MISSING_IF_EXISTS:
        card = ImpactStatementCard(
            statement_index=stmt.statement_index,
            start_line=stmt.start_line,
            end_line=stmt.end_line,
            statement_fingerprint=stmt.statement_fingerprint,
            sanitized_preview=stmt.sanitized_preview,
            analysis_status=AnalysisStatus.ANALYZED,
            execution_prediction=ExecutionPrediction.NO_OP,
            no_op_reason=NoOpReason.COLUMN_MISSING_IF_EXISTS,
            risk=Risk.SAFE,
            confidence=_na_confidence(),
            lock=LockMode.NOT_APPLICABLE,
            table_rewrite=_NA,
            table_scan=_NA,
            index_rebuild=_NA,
            limitations=(AUTHORIZATION_LIMITATION,),
            evidence_refs=(),
            why=("Column is missing and IF EXISTS was written.",),
        )
        return card, ()
    if outcome.kind is EarlyOutcomeKind.COLUMN_MISSING_WOULD_FAIL:
        card = ImpactStatementCard(
            statement_index=stmt.statement_index,
            start_line=stmt.start_line,
            end_line=stmt.end_line,
            statement_fingerprint=stmt.statement_fingerprint,
            sanitized_preview=stmt.sanitized_preview,
            analysis_status=AnalysisStatus.ANALYZED,
            execution_prediction=ExecutionPrediction.WOULD_FAIL,
            no_op_reason=None,
            risk=Risk.CRITICAL,
            confidence=_analyzed_confidence(metrics_present=False),
            lock=LockMode.ACCESS_EXCLUSIVE_LOCK,
            table_rewrite=_NA,
            table_scan=_NA,
            index_rebuild=_NA,
            limitations=(AUTHORIZATION_LIMITATION,),
            evidence_refs=(),
            why=("Column is missing and IF EXISTS was not written.",),
        )
        return card, ()
    # COLUMN_ALREADY_EXISTS_IF_NOT_EXISTS
    card = ImpactStatementCard(
        statement_index=stmt.statement_index,
        start_line=stmt.start_line,
        end_line=stmt.end_line,
        statement_fingerprint=stmt.statement_fingerprint,
        sanitized_preview=stmt.sanitized_preview,
        analysis_status=AnalysisStatus.ANALYZED,
        execution_prediction=ExecutionPrediction.NO_OP,
        no_op_reason=NoOpReason.COLUMN_ALREADY_EXISTS_IF_NOT_EXISTS,
        risk=Risk.WARNING,
        confidence=_analyzed_confidence(metrics_present=False),
        lock=LockMode.ACCESS_EXCLUSIVE_LOCK,
        table_rewrite=_NO,
        table_scan=_NO,
        index_rebuild=_NO,
        limitations=(AUTHORIZATION_LIMITATION,),
        evidence_refs=(),
        why=("Column already exists and IF NOT EXISTS was written.",),
    )
    return card, ()


def _unsupported_card(
    stmt: LocalStatement,
    status: AnalysisStatus,
    *,
    why: str,
) -> ImpactStatementCard:
    return ImpactStatementCard(
        statement_index=stmt.statement_index,
        start_line=stmt.start_line,
        end_line=stmt.end_line,
        statement_fingerprint=stmt.statement_fingerprint,
        sanitized_preview=stmt.sanitized_preview,
        analysis_status=status,
        execution_prediction=ExecutionPrediction.NOT_EVALUATED,
        no_op_reason=None,
        risk=Risk.NOT_APPLICABLE,
        confidence=_na_confidence(),
        lock=LockMode.UNKNOWN,
        table_rewrite=_NA,
        table_scan=_NA,
        index_rebuild=_NA,
        limitations=(),
        evidence_refs=(),
        why=(why,),
    )


def _evidence_kind_for(evidence_id: str) -> EvidenceKind:
    if evidence_id.startswith("rule:"):
        return EvidenceKind.SEMANTIC_RULE
    if evidence_id.startswith("coercion:"):
        return EvidenceKind.SEMANTIC_RULE
    if evidence_id.startswith("dep:"):
        return EvidenceKind.DEPENDENCY_EDGE
    if evidence_id.startswith("index:") or evidence_id.startswith("type:"):
        return EvidenceKind.CATALOG_OBJECT
    return EvidenceKind.SEMANTIC_RULE


def _card_from_verdict(
    stmt: LocalStatement,
    verdict: RuleVerdict,
) -> tuple[ImpactStatementCard, tuple[ImpactEvidence, ...]]:
    evidence = tuple(
        ImpactEvidence(
            evidence_id=eid,
            kind=_evidence_kind_for(eid),
            summary=verdict.rule_key,
            attributes={"rule_key": verdict.rule_key},
        )
        for eid in verdict.evidence_ids
    )
    card = ImpactStatementCard(
        statement_index=stmt.statement_index,
        start_line=stmt.start_line,
        end_line=stmt.end_line,
        statement_fingerprint=stmt.statement_fingerprint,
        sanitized_preview=stmt.sanitized_preview,
        analysis_status=verdict.analysis_status,
        execution_prediction=verdict.execution_prediction,
        no_op_reason=verdict.no_op_reason,
        risk=verdict.risk,
        confidence=verdict.confidence,
        lock=verdict.lock,
        table_rewrite=verdict.table_rewrite,
        table_scan=verdict.table_scan,
        index_rebuild=verdict.index_rebuild,
        limitations=verdict.limitations,
        evidence_refs=tuple(item.evidence_id for item in evidence),
        why=verdict.why,
    )
    return card, evidence


def _unit_base(
    stmt: LocalStatement,
    *,
    family: Literal["type", "add", "drop", "unsupported_parser"],
    ast: object,
    status: AnalysisStatus,
    table_oid: int | None = None,
    table_schema: str | None = None,
    table_name: str | None = None,
    column_attnum: int | None = None,
    column_normalized_name: str | None = None,
    resolution_payload: object | None = None,
    requires_virtual_schema_state: bool = False,
    limitations: tuple[str, ...] = (),
) -> AnalysisUnit:
    return AnalysisUnit(
        statement_index=stmt.statement_index,
        source_span=SourceSpan(stmt.start_line, stmt.end_line, 0, 0),
        statement_fingerprint=stmt.statement_fingerprint,
        sanitized_preview=stmt.sanitized_preview,
        family=family,
        ast=ast,
        analysis_status=status,
        table_oid=table_oid,
        table_schema=table_schema,
        table_name=table_name,
        column_attnum=column_attnum,
        column_normalized_name=column_normalized_name,
        resolution_payload=resolution_payload,
        evidence_ids=(),
        requires_virtual_schema_state=requires_virtual_schema_state,
        limitations=limitations,
    )


def _build_unit_for_statement(
    stmt: LocalStatement,
    *,
    context: ResolutionContext,
    executor: Any,
    connection_context: ImpactConnectionContext,
) -> AnalysisUnit:
    classified = classify_noncontrol_statement(
        stmt.tokens, keyword_categories=context.keyword_categories
    )
    if isinstance(classified, UnsupportedParserAst):
        return _unit_base(
            stmt,
            family="unsupported_parser",
            ast=classified,
            status=AnalysisStatus.UNSUPPORTED_PARSER,
        )

    table_qn = classified.table.qualified_name
    schema = _schema_name(table_qn)
    relname = _ident_name(table_qn)
    column_name = classified.column.normalized_value
    family: Literal["type", "add", "drop"] = classified.family

    relation_res = resolve_relation(schema=schema, name=relname, context=context, executor=executor)

    if relation_res.status == "unsupported_resolution":
        return _unit_base(
            stmt,
            family=family,
            ast=classified,
            status=AnalysisStatus.UNSUPPORTED_RESOLUTION,
            table_schema=schema,
            table_name=relname,
            column_normalized_name=column_name,
        )

    if relation_res.status == "not_found":
        # Deterministic missing only for qualified names (design §2.5).
        if schema is None:
            return _unit_base(
                stmt,
                family=family,
                ast=classified,
                status=AnalysisStatus.UNSUPPORTED_RESOLUTION,
                table_name=relname,
                column_normalized_name=column_name,
            )
        early = (
            EarlySemanticOutcome(EarlyOutcomeKind.TARGET_MISSING_IF_EXISTS)
            if classified.table.if_exists
            else EarlySemanticOutcome(EarlyOutcomeKind.TARGET_MISSING_WOULD_FAIL)
        )
        return _unit_base(
            stmt,
            family=family,
            ast=classified,
            status=AnalysisStatus.ANALYZED,
            table_schema=schema,
            table_name=relname,
            column_normalized_name=column_name,
            resolution_payload=early,
        )

    assert relation_res.oid is not None
    relation = fetch_relation_snapshot(executor, relation_res.oid)
    if relation is None:
        # Existing oid vanished between resolve and fetch — required evidence missing.
        return _unit_base(
            stmt,
            family=family,
            ast=classified,
            status=AnalysisStatus.UNSUPPORTED_EVIDENCE,
            table_oid=relation_res.oid,
            table_schema=relation_res.nspname,
            table_name=relation_res.relname,
            column_normalized_name=column_name,
        )

    column = _find_column(relation, column_name)

    if isinstance(classified, (SupportedAlterDrop, SupportedAlterType)) and column is None:
        column_if_exists = isinstance(classified, SupportedAlterDrop) and classified.if_exists
        early = (
            EarlySemanticOutcome(EarlyOutcomeKind.COLUMN_MISSING_IF_EXISTS)
            if column_if_exists
            else EarlySemanticOutcome(EarlyOutcomeKind.COLUMN_MISSING_WOULD_FAIL)
        )
        return _unit_base(
            stmt,
            family=family,
            ast=classified,
            status=AnalysisStatus.ANALYZED,
            table_oid=relation.oid,
            table_schema=relation.nspname,
            table_name=relation.relname,
            column_normalized_name=column_name,
            resolution_payload=early,
        )

    if (
        isinstance(classified, SupportedAlterAdd)
        and column is not None
        and classified.if_not_exists
    ):
        return _unit_base(
            stmt,
            family=family,
            ast=classified,
            status=AnalysisStatus.ANALYZED,
            table_oid=relation.oid,
            table_schema=relation.nspname,
            table_name=relation.relname,
            column_attnum=column.attnum,
            column_normalized_name=column_name,
            resolution_payload=EarlySemanticOutcome(
                EarlyOutcomeKind.COLUMN_ALREADY_EXISTS_IF_NOT_EXISTS
            ),
        )

    metrics = fetch_relation_metrics(executor, relation.oid)
    metrics_present = metrics is not None
    n_live_tup = metrics.n_live_tup if metrics is not None else None
    server_major = connection_context.server_major

    source_type: TypeSnapshot | None = None
    target_type: TypeSnapshot | None = None
    pg_cast_rows: tuple[Any, ...] = ()
    dependency_edges: tuple[Any, ...] = ()
    dependency_graph_complete = True
    truncated_at_limit = False
    using_present = False
    effective_behavior: Literal["restrict", "cascade"] | None = None
    if_not_exists = False
    nullability: Literal["unspecified", "null", "not_null"] | None = None
    has_default_tokens = False

    if isinstance(classified, SupportedAlterType):
        using_present = bool(classified.using_expression_tokens)
        if column is None:
            return _unit_base(
                stmt,
                family=family,
                ast=classified,
                status=AnalysisStatus.UNSUPPORTED_EVIDENCE,
                table_oid=relation.oid,
                table_schema=relation.nspname,
                table_name=relation.relname,
                column_normalized_name=column_name,
            )
        source_type = fetch_type_snapshot(executor, column.type_oid)
        target_res = _resolve_type_name(classified.type_name.name, context, executor)
        if target_res is None:
            return _unit_base(
                stmt,
                family=family,
                ast=classified,
                status=AnalysisStatus.UNSUPPORTED_RESOLUTION,
                table_oid=relation.oid,
                table_schema=relation.nspname,
                table_name=relation.relname,
                column_attnum=column.attnum,
                column_normalized_name=column_name,
            )
        target_type = fetch_type_snapshot(executor, target_res)
        if source_type is None or target_type is None:
            return _unit_base(
                stmt,
                family=family,
                ast=classified,
                status=AnalysisStatus.UNSUPPORTED_EVIDENCE,
                table_oid=relation.oid,
                table_schema=relation.nspname,
                table_name=relation.relname,
                column_attnum=column.attnum,
                column_normalized_name=column_name,
            )
        pg_cast_rows = tuple(fetch_pg_cast_rows(executor, source_type.oid, target_type.oid))

    elif isinstance(classified, SupportedAlterAdd):
        if_not_exists = classified.if_not_exists
        nullability = classified.nullability
        has_default_tokens = bool(classified.default_expression_tokens)
        target_res = _resolve_type_name(classified.type_name.name, context, executor)
        if target_res is None:
            return _unit_base(
                stmt,
                family=family,
                ast=classified,
                status=AnalysisStatus.UNSUPPORTED_RESOLUTION,
                table_oid=relation.oid,
                table_schema=relation.nspname,
                table_name=relation.relname,
                column_normalized_name=column_name,
            )
        target_type = fetch_type_snapshot(executor, target_res)
        if target_type is None:
            return _unit_base(
                stmt,
                family=family,
                ast=classified,
                status=AnalysisStatus.UNSUPPORTED_EVIDENCE,
                table_oid=relation.oid,
                table_schema=relation.nspname,
                table_name=relation.relname,
                column_normalized_name=column_name,
            )

    elif isinstance(classified, SupportedAlterDrop):
        effective_behavior = classified.effective_behavior
        if column is None:
            return _unit_base(
                stmt,
                family=family,
                ast=classified,
                status=AnalysisStatus.UNSUPPORTED_EVIDENCE,
                table_oid=relation.oid,
                table_schema=relation.nspname,
                table_name=relation.relname,
                column_normalized_name=column_name,
            )
        dependency_edges, truncated_at_limit = gather_dependency_edges(
            executor,
            roots=((0, relation.oid, column.attnum),),
        )
        dependency_graph_complete = not truncated_at_limit

    payload = CatalogBoundPayload(
        family=family,
        relation=relation,
        column=column,
        source_type=source_type,
        target_type=target_type,
        pg_cast_rows=pg_cast_rows,
        dependency_edges=dependency_edges,
        dependency_graph_complete=dependency_graph_complete,
        truncated_at_limit=truncated_at_limit,
        metrics_present=metrics_present,
        n_live_tup=n_live_tup,
        server_major=server_major,
        using_present=using_present,
        effective_behavior=effective_behavior,
        if_not_exists=if_not_exists,
        nullability=nullability,
        has_default_tokens=has_default_tokens,
    )
    return _unit_base(
        stmt,
        family=family,
        ast=classified,
        status=AnalysisStatus.ANALYZED,
        table_oid=relation.oid,
        table_schema=relation.nspname,
        table_name=relation.relname,
        column_attnum=column.attnum if column is not None else None,
        column_normalized_name=column_name,
        resolution_payload=payload,
        requires_virtual_schema_state=isinstance(classified, SupportedAlterAdd),
    )


def _resolve_type_name(
    qualified: QualifiedName,
    context: ResolutionContext,
    executor: Any,
) -> int | None:
    if qualified.is_multiword_builtin:
        res = resolve_type(
            schema="pg_catalog",
            name=qualified.normalized,
            context=context,
            executor=executor,
        )
        # Multiword builtins may also be looked up unqualified by normalized phrase.
        if res.status != "resolved":
            res = resolve_type(
                schema=None,
                name=qualified.normalized,
                context=context,
                executor=executor,
            )
    else:
        res = resolve_type(
            schema=_schema_name(qualified),
            name=_ident_name(qualified),
            context=context,
            executor=executor,
        )
    if res.status != "resolved" or res.oid is None:
        return None
    return res.oid


def _evaluate_unit(
    unit: AnalysisUnit, stmt: LocalStatement
) -> tuple[ImpactStatementCard, tuple[ImpactEvidence, ...]]:
    if unit.analysis_status is not AnalysisStatus.ANALYZED:
        return (
            _unsupported_card(
                stmt,
                unit.analysis_status,
                why=f"Statement marked {unit.analysis_status.value}.",
            ),
            (),
        )

    payload = unit.resolution_payload
    if isinstance(payload, EarlySemanticOutcome):
        return _card_from_early(stmt, payload)

    if not isinstance(payload, CatalogBoundPayload):
        return (
            _unsupported_card(
                stmt,
                AnalysisStatus.UNSUPPORTED_EVIDENCE,
                why="Required catalog evidence is missing.",
            ),
            (),
        )

    if payload.family == "type":
        assert payload.column is not None
        assert payload.source_type is not None
        assert payload.target_type is not None
        facts = TypeChangeFacts(
            server_major=payload.server_major,
            source_type_name=payload.source_type.typname,
            target_type_name=payload.target_type.typname,
            source_typmod=payload.column.typmod,
            target_typmod=payload.target_type.typtypmod,
            source_collation_oid=payload.column.collation_oid,
            target_collation_oid=payload.target_type.typcollation or None,
            source_is_domain=payload.source_type.typtype == "d",
            target_is_domain=payload.target_type.typtype == "d",
            using_present=payload.using_present,
            using_identity_proven=False,
            affected_indexes_exist=_indexes_on_column(payload.relation, payload.column.attnum),
            metrics_present=payload.metrics_present,
            pg_cast_rows=tuple(payload.pg_cast_rows),
            table_exists=True,
        )
        return _card_from_verdict(stmt, evaluate_type_change(facts))

    if payload.family == "add":
        assert payload.target_type is not None
        nullable = payload.nullability != "not_null"
        domain_has_constraints = bool(payload.target_type.domain_constraints)
        has_domain_default = payload.target_type.typtype == "d" and (
            payload.target_type.typdefaultbin is not None
            or payload.target_type.typdefault is not None
        )
        if payload.has_default_tokens:
            effective_kind: Literal[
                "null", "explicit_null", "column_expression", "domain_expression"
            ] = "column_expression"
            volatility: Literal["proven_nonvolatile", "proven_volatile", "unknown"] = "unknown"
            coercion: Literal["proven_valid", "proven_invalid", "unknown"] = "unknown"
            nullability_axis: Literal["proven_nonnull", "proven_null", "unknown"] = "unknown"
        elif has_domain_default:
            effective_kind = "domain_expression"
            volatility = "unknown"
            coercion = "unknown"
            nullability_axis = "unknown"
        else:
            effective_kind = "null"
            volatility = "proven_nonvolatile"
            coercion = "proven_valid"
            nullability_axis = "proven_null"
        facts_add = AddColumnFacts(
            server_major=payload.server_major,
            nullable=nullable,
            indexes_exist=bool(payload.relation.indexes),
            metrics_present=payload.metrics_present,
            n_live_tup=payload.n_live_tup,
            effective_default_kind=effective_kind,
            default_volatility=volatility,
            default_coercion=coercion,
            default_nullability=nullability_axis,
            domain_has_constraints=domain_has_constraints,
            target_type=payload.target_type,
            index_names=tuple(idx.relname for idx in payload.relation.indexes),
        )
        return _card_from_verdict(stmt, evaluate_add_column(facts_add))

    # drop
    assert payload.column is not None
    assert payload.effective_behavior is not None
    facts_drop = DropColumnFacts(
        table_exists=True,
        column_exists=True,
        effective_behavior=payload.effective_behavior,
        dependency_edges=tuple(payload.dependency_edges),
        dependency_graph_complete=payload.dependency_graph_complete,
        truncated_at_limit=payload.truncated_at_limit,
        required_evidence_missing=False,
        metrics_present=payload.metrics_present,
    )
    return _card_from_verdict(stmt, evaluate_drop_column(facts_drop))


def _assemble_completed(
    *,
    script: LocalParsedScript,
    cards: Sequence[ImpactStatementCard],
    evidence: Sequence[ImpactEvidence],
    connection_context: ImpactConnectionContext,
    snapshot: ImpactSnapshot,
    started_at: datetime,
    duration_ms: int,
    stage: AnalysisStage,
) -> ImpactCommandResult:
    incomplete = any(card.analysis_status.value.startswith("unsupported_") for card in cards)
    exit_code = aggregate_exit_code(preflight_incomplete=False, statements=cards)
    if incomplete:
        outcome = Outcome.INCOMPLETE
        assert exit_code == 3
    else:
        outcome = Outcome.COMPLETED
        assert exit_code in (0, 1, 2)
    return ImpactCommandResult(
        outcome=outcome,
        exit_code=exit_code,  # type: ignore[arg-type]
        started_at=started_at,
        duration_ms=duration_ms,
        app_version=get_app_version(),
        input=ImpactInputMeta(
            path_basename=script.path_basename,
            source_statement_count=script.source_statement_count,
            card_count=len(cards),
            control_statement_count=len(script.control_ordinals),
        ),
        connection_context=connection_context,
        preflight=ImpactPreflight(
            status=PreflightStatus.PASSED,
            analysis_stage_reached=stage,
            checks=(),
            limitations=(),
        ),
        snapshot=snapshot,
        summary=_summarize(cards, incomplete=incomplete),
        statements=tuple(cards),
        evidence=tuple(evidence),
        error=None,
    )


def run_impact(
    path: Path,
    connection_config: ConnectionConfig,
    session_safety: SessionSafetyConfig,
) -> ImpactCommandResult:
    """Raise `LocalPhaseError` for exit-4 local failures; otherwise return a result."""
    started_at = _now()
    t0 = time.perf_counter_ns()

    def elapsed_ms() -> int:
        return max(0, (time.perf_counter_ns() - t0) // 1_000_000)

    script = parse_migration_path(path)

    connection_opened = False
    try:
        with open_connection(connection_config) as conn:
            connection_opened = True
            session = DiagnosticSession(conn, session_safety)
            try:
                profile: ImpactSessionState = session.establish_impact_profile()
                context = profile.resolution_context
                connection_context = profile.connection_context

                preflight = evaluate_preflight_gates(connection_context)
                if preflight.incomplete:
                    checks = tuple(
                        ImpactPreflightCheck(
                            id=failure.check_id,
                            status=ImpactPreflightCheckStatus.FAILED,
                            detail=failure.detail,
                        )
                        for failure in preflight.failures
                    )
                    return ImpactCommandResult(
                        outcome=Outcome.INCOMPLETE,
                        exit_code=3,
                        started_at=started_at,
                        duration_ms=elapsed_ms(),
                        app_version=get_app_version(),
                        input=ImpactInputMeta(
                            path_basename=script.path_basename,
                            source_statement_count=script.source_statement_count,
                            card_count=0,
                            control_statement_count=len(script.control_ordinals),
                        ),
                        connection_context=connection_context,
                        preflight=ImpactPreflight(
                            status=PreflightStatus.INCOMPLETE,
                            analysis_stage_reached=AnalysisStage.PREFLIGHT,
                            checks=checks,
                            limitations=(),
                        ),
                        snapshot=None,
                        summary=_empty_summary(incomplete=True),
                        statements=(),
                        evidence=(),
                        error=None,
                    )

                executor = session.as_query_executor()
                stmt_by_index: dict[int, LocalStatement] = {
                    stmt.statement_index: stmt for stmt in script.statements
                }
                units: list[AnalysisUnit] = []
                for stmt in script.statements:
                    if stmt.is_control:
                        continue
                    units.append(
                        _build_unit_for_statement(
                            stmt,
                            context=context,
                            executor=executor,
                            connection_context=connection_context,
                        )
                    )

                sequenced = apply_sequence_constraints(units)
                cards: list[ImpactStatementCard] = []
                evidence_acc: list[ImpactEvidence] = []
                seen_evidence: set[str] = set()
                for unit in sequenced:
                    stmt = stmt_by_index[unit.statement_index]
                    card, evs = _evaluate_unit(unit, stmt)
                    cards.append(card)
                    for ev in evs:
                        if ev.evidence_id not in seen_evidence:
                            seen_evidence.add(ev.evidence_id)
                            evidence_acc.append(ev)

                cards_sorted = tuple(sorted(cards, key=lambda c: c.statement_index))
                snapshot = ImpactSnapshot(
                    catalog_snapshot_at=profile.catalog_snapshot_at,
                    metrics_observed_at=None,
                    metrics_consistency="best_effort",
                    server_version_num=connection_context.server_version_num,
                )
                return _assemble_completed(
                    script=script,
                    cards=cards_sorted,
                    evidence=evidence_acc,
                    connection_context=connection_context,
                    snapshot=snapshot,
                    started_at=started_at,
                    duration_ms=elapsed_ms(),
                    stage=AnalysisStage.COMPLETE,
                )
            finally:
                if connection_opened:
                    _force_rollback(conn)
    except LocalPhaseError:
        raise
    except SessionSafetyError as exc:
        return _failed_result(
            script=script,
            started_at=started_at,
            duration_ms=elapsed_ms(),
            error=_execution_error_session_safety(exc),
            stage=AnalysisStage.PREFLIGHT,
        )
    except PginspectConnectError as exc:
        return _failed_result(
            script=script,
            started_at=started_at,
            duration_ms=elapsed_ms(),
            error=_execution_error_from_connect(exc),
            stage=AnalysisStage.CONNECT,
        )
    except PginspectInternalError as exc:
        return _failed_result(
            script=script,
            started_at=started_at,
            duration_ms=elapsed_ms(),
            error=_execution_error_internal(exc),
            stage=AnalysisStage.CONNECT,
        )
    except Exception as exc:
        wrapped = PginspectInternalError(
            "unexpected error in run_impact",
            driver_exception_type=type(exc).__name__,
        )
        return _failed_result(
            script=script,
            started_at=started_at,
            duration_ms=elapsed_ms(),
            error=_execution_error_internal(wrapped),
            stage=AnalysisStage.CONNECT,
        )
