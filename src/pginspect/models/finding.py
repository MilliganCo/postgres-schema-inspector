"""Discriminated Finding models with typed evidence (schema 1.0)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, model_validator

from pginspect.models.base import PublicModel
from pginspect.models.context import ConnectionTargetContext
from pginspect.models.enums import (
    ClassificationSource,
    FindingId,
    FindingStatus,
    SessionSafetyMisconfigurationCategory,
    Severity,
)


class ConnectionFindingScope(PublicModel):
    target: ConnectionTargetContext


class Remediation(PublicModel):
    summary: str


class ConnectionEstablishedEvidence(PublicModel):
    tls_used: bool | None


class ConnectionFailedEvidence(PublicModel):
    category: Literal[
        "authentication_failed",
        "network_unreachable",
        "connect_timeout",
        "tls_failed",
        "database_missing",
        "connection_failed",
    ]
    classification_source: ClassificationSource
    sqlstate: str | None


class _ServerVersionEvidenceBase(PublicModel):
    server_version: str
    server_version_num: int
    server_major: int | None
    server_major_label: str
    supported_majors: tuple[int, ...]
    max_tested_stable_major: int
    tested_prerelease_majors: tuple[int, ...]


class ServerVersionSupportedEvidence(_ServerVersionEvidenceBase):
    version_support: Literal["supported"]


class ServerVersionExperimentalEvidence(_ServerVersionEvidenceBase):
    version_support: Literal["experimental"]


class ServerVersionUntestedEvidence(_ServerVersionEvidenceBase):
    version_support: Literal["untested_newer"]


class ServerVersionUnsupportedEvidence(_ServerVersionEvidenceBase):
    version_support: Literal["unsupported_older", "unsupported_legacy"]


class SessionSafetyVerifiedEvidence(PublicModel):
    default_transaction_read_only: Literal[True]
    transaction_read_only: Literal[True]
    statement_timeout_ms: int
    lock_timeout_ms: int
    idle_in_transaction_session_timeout_ms: int
    search_path: tuple[Literal["pg_catalog"]]
    application_name_kind: Literal["pginspect_owned", "custom", "empty"]
    application_name_value: str | None
    write_probe: Literal["not_run"]
    verification_level: Literal["settings"]
    read_only_scope: Literal["postgresql_transaction"]
    read_only_is_sandbox: Literal[False]

    @model_validator(mode="after")
    def validate_application_name(self) -> SessionSafetyVerifiedEvidence:
        if self.application_name_kind == "pginspect_owned":
            if not self.application_name_value:
                raise ValueError(
                    "application_name_value is required when application_name_kind is pginspect_owned"
                )
        elif self.application_name_value is not None:
            raise ValueError(
                "application_name_value must be null when application_name_kind is custom or empty"
            )
        return self


class SessionSafetyExpectedState(PublicModel):
    default_transaction_read_only: Literal[True]
    transaction_read_only: Literal[True]
    statement_timeout_ms: int
    lock_timeout_ms: int
    idle_in_transaction_session_timeout_ms: int
    search_path: tuple[Literal["pg_catalog"]]


class SessionSafetyObservedState(PublicModel):
    default_transaction_read_only: bool
    transaction_read_only: bool
    statement_timeout_ms: int
    lock_timeout_ms: int
    idle_in_transaction_session_timeout_ms: int
    search_path: tuple[str, ...]


class SessionSafetyMisconfiguredEvidence(PublicModel):
    category: SessionSafetyMisconfigurationCategory
    expected: SessionSafetyExpectedState
    observed: SessionSafetyObservedState | None
    sqlstate: str | None

    @model_validator(mode="after")
    def validate_category_invariants(self) -> SessionSafetyMisconfiguredEvidence:
        if self.category is SessionSafetyMisconfigurationCategory.SET_REJECTED:
            if self.observed is not None:
                raise ValueError("observed must be null when category is set_rejected")
            return self

        if self.category is SessionSafetyMisconfigurationCategory.VERIFICATION_MISMATCH:
            if self.observed is None:
                raise ValueError("observed is required when category is verification_mismatch")
            expected = self.expected
            observed = self.observed
            differs = (
                observed.default_transaction_read_only != expected.default_transaction_read_only
                or observed.transaction_read_only != expected.transaction_read_only
                or observed.statement_timeout_ms != expected.statement_timeout_ms
                or observed.lock_timeout_ms != expected.lock_timeout_ms
                or observed.idle_in_transaction_session_timeout_ms
                != expected.idle_in_transaction_session_timeout_ms
                or tuple(observed.search_path) != tuple(expected.search_path)
            )
            if not differs:
                raise ValueError(
                    "observed must differ from expected when category is verification_mismatch"
                )
        return self


class FindingBase(PublicModel):
    schema_version: Literal["1.0"] = "1.0"
    title: str
    summary: str | None = None
    scope: ConnectionFindingScope
    limitations: tuple[str, ...] = ()
    remediation: Remediation | None = None


class ConnectionEstablishedFinding(FindingBase):
    id: Literal[FindingId.CONNECTION_ESTABLISHED] = FindingId.CONNECTION_ESTABLISHED
    severity: Literal[Severity.OK] = Severity.OK
    confidence: Literal["high"] = "high"
    status: Literal[FindingStatus.PASSED] = FindingStatus.PASSED
    evidence: ConnectionEstablishedEvidence


class ConnectionFailedFinding(FindingBase):
    id: Literal[FindingId.CONNECTION_FAILED] = FindingId.CONNECTION_FAILED
    severity: Literal[Severity.CRITICAL] = Severity.CRITICAL
    confidence: Literal["high"] = "high"
    status: Literal[FindingStatus.TRIGGERED] = FindingStatus.TRIGGERED
    evidence: ConnectionFailedEvidence


class ServerVersionSupportedFinding(FindingBase):
    id: Literal[FindingId.CONNECTION_SERVER_VERSION_SUPPORTED] = (
        FindingId.CONNECTION_SERVER_VERSION_SUPPORTED
    )
    severity: Literal[Severity.OK] = Severity.OK
    confidence: Literal["high"] = "high"
    status: Literal[FindingStatus.PASSED] = FindingStatus.PASSED
    evidence: ServerVersionSupportedEvidence


class ServerVersionExperimentalFinding(FindingBase):
    id: Literal[FindingId.CONNECTION_SERVER_VERSION_EXPERIMENTAL] = (
        FindingId.CONNECTION_SERVER_VERSION_EXPERIMENTAL
    )
    severity: Literal[Severity.WARNING] = Severity.WARNING
    confidence: Literal["high"] = "high"
    status: Literal[FindingStatus.TRIGGERED] = FindingStatus.TRIGGERED
    evidence: ServerVersionExperimentalEvidence


class ServerVersionUntestedFinding(FindingBase):
    id: Literal[FindingId.CONNECTION_SERVER_VERSION_UNTESTED] = (
        FindingId.CONNECTION_SERVER_VERSION_UNTESTED
    )
    severity: Literal[Severity.WARNING] = Severity.WARNING
    confidence: Literal["high"] = "high"
    status: Literal[FindingStatus.TRIGGERED] = FindingStatus.TRIGGERED
    evidence: ServerVersionUntestedEvidence


class ServerVersionUnsupportedFinding(FindingBase):
    id: Literal[FindingId.CONNECTION_SERVER_VERSION_UNSUPPORTED] = (
        FindingId.CONNECTION_SERVER_VERSION_UNSUPPORTED
    )
    severity: Literal[Severity.CRITICAL] = Severity.CRITICAL
    confidence: Literal["high"] = "high"
    status: Literal[FindingStatus.TRIGGERED] = FindingStatus.TRIGGERED
    evidence: ServerVersionUnsupportedEvidence


class SessionSafetyVerifiedFinding(FindingBase):
    id: Literal[FindingId.CONNECTION_SESSION_SAFETY_VERIFIED] = (
        FindingId.CONNECTION_SESSION_SAFETY_VERIFIED
    )
    severity: Literal[Severity.OK] = Severity.OK
    confidence: Literal["high"] = "high"
    status: Literal[FindingStatus.PASSED] = FindingStatus.PASSED
    evidence: SessionSafetyVerifiedEvidence


class SessionSafetyMisconfiguredFinding(FindingBase):
    id: Literal[FindingId.CONNECTION_SESSION_SAFETY_MISCONFIGURED] = (
        FindingId.CONNECTION_SESSION_SAFETY_MISCONFIGURED
    )
    severity: Literal[Severity.CRITICAL] = Severity.CRITICAL
    confidence: Literal["high"] = "high"
    status: Literal[FindingStatus.TRIGGERED] = FindingStatus.TRIGGERED
    evidence: SessionSafetyMisconfiguredEvidence


Finding = Annotated[
    ConnectionEstablishedFinding
    | ConnectionFailedFinding
    | ServerVersionSupportedFinding
    | ServerVersionExperimentalFinding
    | ServerVersionUntestedFinding
    | ServerVersionUnsupportedFinding
    | SessionSafetyVerifiedFinding
    | SessionSafetyMisconfiguredFinding,
    Field(discriminator="id"),
]

finding_adapter: TypeAdapter[Finding] = TypeAdapter(Finding)
