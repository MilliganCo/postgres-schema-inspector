"""Impact-domain enums (schema 0.1, design section 4.2 / 3.4 / 3.5)."""

from __future__ import annotations

from enum import StrEnum


class Outcome(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class Risk(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    SAFE = "safe"
    NOT_APPLICABLE = "not_applicable"


class AnalysisStatus(StrEnum):
    ANALYZED = "analyzed"
    UNSUPPORTED_PARSER = "unsupported_parser"
    UNSUPPORTED_RESOLUTION = "unsupported_resolution"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    UNSUPPORTED_EVIDENCE = "unsupported_evidence"
    UNSUPPORTED_SEQUENCE = "unsupported_sequence"


class ExecutionPrediction(StrEnum):
    APPLIES = "applies"
    NO_OP = "no_op"
    WOULD_FAIL = "would_fail"
    MAY_FAIL = "may_fail"
    NOT_EVALUATED = "not_evaluated"


class LockMode(StrEnum):
    ACCESS_EXCLUSIVE_LOCK = "AccessExclusiveLock"
    SHARE_UPDATE_EXCLUSIVE_LOCK = "ShareUpdateExclusiveLock"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class PhysicalTriState(StrEnum):
    YES = "yes"
    NO = "no"
    POSSIBLE = "possible"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class NoOpReason(StrEnum):
    TARGET_MISSING_IF_EXISTS = "target_missing_if_exists"
    COLUMN_MISSING_IF_EXISTS = "column_missing_if_exists"
    COLUMN_ALREADY_EXISTS_IF_NOT_EXISTS = "column_already_exists_if_not_exists"


class ImpactRole(StrEnum):
    TARGET = "target"
    INTERNAL = "internal"
    AUTOMATIC = "automatic"
    BLOCKER = "blocker"
    CASCADE = "cascade"
    REBUILT = "rebuilt"
    RELATED = "related"


class EvidenceKind(StrEnum):
    SERVER_FACT = "server_fact"
    CATALOG_OBJECT = "catalog_object"
    DEPENDENCY_EDGE = "dependency_edge"
    METRIC_OBSERVATION = "metric_observation"
    SEMANTIC_RULE = "semantic_rule"


class ObjectKind(StrEnum):
    TABLE = "table"
    COLUMN = "column"
    INDEX = "index"
    CONSTRAINT = "constraint"
    VIEW = "view"
    FUNCTION = "function"
    TYPE = "type"
    COLLATION = "collation"
    OTHER = "other"


class PreflightStatus(StrEnum):
    PASSED = "passed"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class ImpactPreflightCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AnalysisStage(StrEnum):
    CONNECT = "connect"
    PREFLIGHT = "preflight"
    PARSE = "parse"
    RESOLVE = "resolve"
    CATALOG = "catalog"
    RULES = "rules"
    COMPLETE = "complete"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOT_APPLICABLE = "not_applicable"


class ImpactScaleConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
