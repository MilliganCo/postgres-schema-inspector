from __future__ import annotations

from pginspect.impact.models.enums import (
    AnalysisStage,
    AnalysisStatus,
    ConfidenceLevel,
    EvidenceKind,
    ExecutionPrediction,
    ImpactPreflightCheckStatus,
    ImpactRole,
    ImpactScaleConfidence,
    LockMode,
    NoOpReason,
    ObjectKind,
    Outcome,
    PhysicalTriState,
    PreflightStatus,
    Risk,
)


def test_impact_preflight_check_status_values() -> None:
    assert {member.value for member in ImpactPreflightCheckStatus} == {
        "passed",
        "failed",
        "skipped",
    }


def test_preflight_status_values() -> None:
    assert {member.value for member in PreflightStatus} == {"passed", "incomplete", "failed"}


def test_outcome_values() -> None:
    assert {member.value for member in Outcome} == {"completed", "incomplete", "failed"}


def test_risk_values() -> None:
    assert {member.value for member in Risk} == {"critical", "warning", "safe", "not_applicable"}


def test_analysis_status_values() -> None:
    assert {member.value for member in AnalysisStatus} == {
        "analyzed",
        "unsupported_parser",
        "unsupported_resolution",
        "unsupported_scope",
        "unsupported_evidence",
        "unsupported_sequence",
    }


def test_execution_prediction_values() -> None:
    assert {member.value for member in ExecutionPrediction} == {
        "applies",
        "no_op",
        "would_fail",
        "may_fail",
        "not_evaluated",
    }


def test_lock_mode_values_match_design_case_exactly() -> None:
    assert {member.value for member in LockMode} == {
        "AccessExclusiveLock",
        "ShareUpdateExclusiveLock",
        "not_applicable",
        "unknown",
    }
    assert LockMode.ACCESS_EXCLUSIVE_LOCK.value == "AccessExclusiveLock"
    assert LockMode.SHARE_UPDATE_EXCLUSIVE_LOCK.value == "ShareUpdateExclusiveLock"


def test_physical_tri_state_values() -> None:
    assert {member.value for member in PhysicalTriState} == {
        "yes",
        "no",
        "possible",
        "unknown",
        "not_applicable",
    }


def test_no_op_reason_values() -> None:
    assert {member.value for member in NoOpReason} == {
        "target_missing_if_exists",
        "column_missing_if_exists",
        "column_already_exists_if_not_exists",
    }


def test_impact_role_values() -> None:
    assert {member.value for member in ImpactRole} == {
        "target",
        "internal",
        "automatic",
        "blocker",
        "cascade",
        "rebuilt",
        "related",
    }


def test_evidence_kind_values() -> None:
    assert {member.value for member in EvidenceKind} == {
        "server_fact",
        "catalog_object",
        "dependency_edge",
        "metric_observation",
        "semantic_rule",
    }


def test_object_kind_values() -> None:
    assert {member.value for member in ObjectKind} == {
        "table",
        "column",
        "index",
        "constraint",
        "view",
        "function",
        "type",
        "collation",
        "other",
    }


def test_analysis_stage_values() -> None:
    assert {member.value for member in AnalysisStage} == {
        "connect",
        "preflight",
        "parse",
        "resolve",
        "catalog",
        "rules",
        "complete",
    }


def test_confidence_level_values() -> None:
    assert {member.value for member in ConfidenceLevel} == {
        "high",
        "medium",
        "low",
        "not_applicable",
    }


def test_impact_scale_confidence_values() -> None:
    assert {member.value for member in ImpactScaleConfidence} == {
        "high",
        "medium",
        "low",
        "unknown",
        "not_applicable",
    }


def test_impact_preflight_check_status_is_distinct_enum_from_preflight_status() -> None:
    assert ImpactPreflightCheckStatus is not PreflightStatus
    assert {m.value for m in ImpactPreflightCheckStatus} != {m.value for m in PreflightStatus}
