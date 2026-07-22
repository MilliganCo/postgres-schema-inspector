"""Unit tests for Finding discriminated union and evidence invariants."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from pginspect.models.context import ConnectionTargetContext
from pginspect.models.enums import (
    ClassificationSource,
    ConnectionTargetSource,
    FindingId,
    SessionSafetyMisconfigurationCategory,
    Severity,
)
from pginspect.models.finding import (
    ConnectionEstablishedEvidence,
    ConnectionEstablishedFinding,
    ConnectionFailedEvidence,
    ConnectionFailedFinding,
    ConnectionFindingScope,
    Finding,
    Remediation,
    ServerVersionSupportedEvidence,
    ServerVersionSupportedFinding,
    SessionSafetyExpectedState,
    SessionSafetyMisconfiguredEvidence,
    SessionSafetyMisconfiguredFinding,
    SessionSafetyObservedState,
    SessionSafetyVerifiedEvidence,
    SessionSafetyVerifiedFinding,
)


def _scope() -> ConnectionFindingScope:
    return ConnectionFindingScope(
        target=ConnectionTargetContext(
            explicit_host_fingerprint=None,
            source=ConnectionTargetSource.LIBPQ_RESOLVED_UNKNOWN,
        )
    )


def test_server_version_supported_rejects_unsupported_older() -> None:
    with pytest.raises(ValidationError):
        ServerVersionSupportedEvidence(
            server_version="13.8",
            server_version_num=130008,
            server_major=13,
            server_major_label="13",
            version_support="unsupported_older",  # type: ignore[arg-type]
            supported_majors=(14, 15, 16, 17, 18),
            max_tested_stable_major=18,
            tested_prerelease_majors=(19,),
        )


def test_session_safety_verified_rejects_transaction_read_only_false() -> None:
    with pytest.raises(ValidationError):
        SessionSafetyVerifiedEvidence(
            default_transaction_read_only=True,
            transaction_read_only=False,  # type: ignore[arg-type]
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
        )


def test_set_rejected_requires_observed_none() -> None:
    expected = SessionSafetyExpectedState(
        default_transaction_read_only=True,
        transaction_read_only=True,
        statement_timeout_ms=15000,
        lock_timeout_ms=2000,
        idle_in_transaction_session_timeout_ms=15000,
        search_path=("pg_catalog",),
    )
    observed = SessionSafetyObservedState(
        default_transaction_read_only=True,
        transaction_read_only=True,
        statement_timeout_ms=15000,
        lock_timeout_ms=2000,
        idle_in_transaction_session_timeout_ms=15000,
        search_path=("pg_catalog",),
    )
    with pytest.raises(ValidationError):
        SessionSafetyMisconfiguredEvidence(
            category=SessionSafetyMisconfigurationCategory.SET_REJECTED,
            expected=expected,
            observed=observed,
            sqlstate="42501",
        )


def test_verification_mismatch_requires_observed_and_diff() -> None:
    expected = SessionSafetyExpectedState(
        default_transaction_read_only=True,
        transaction_read_only=True,
        statement_timeout_ms=15000,
        lock_timeout_ms=2000,
        idle_in_transaction_session_timeout_ms=15000,
        search_path=("pg_catalog",),
    )
    same = SessionSafetyObservedState(
        default_transaction_read_only=True,
        transaction_read_only=True,
        statement_timeout_ms=15000,
        lock_timeout_ms=2000,
        idle_in_transaction_session_timeout_ms=15000,
        search_path=("pg_catalog",),
    )
    with pytest.raises(ValidationError):
        SessionSafetyMisconfiguredEvidence(
            category=SessionSafetyMisconfigurationCategory.VERIFICATION_MISMATCH,
            expected=expected,
            observed=None,
            sqlstate=None,
        )
    with pytest.raises(ValidationError):
        SessionSafetyMisconfiguredEvidence(
            category=SessionSafetyMisconfigurationCategory.VERIFICATION_MISMATCH,
            expected=expected,
            observed=same,
            sqlstate=None,
        )


def test_application_name_custom_requires_null_value() -> None:
    with pytest.raises(ValidationError):
        SessionSafetyVerifiedEvidence(
            default_transaction_read_only=True,
            transaction_read_only=True,
            statement_timeout_ms=15000,
            lock_timeout_ms=2000,
            idle_in_transaction_session_timeout_ms=15000,
            search_path=("pg_catalog",),
            application_name_kind="custom",
            application_name_value="my-app",
            write_probe="not_run",
            verification_level="settings",
            read_only_scope="postgresql_transaction",
            read_only_is_sandbox=False,
        )


def test_confidence_only_accepts_high() -> None:
    with pytest.raises(ValidationError):
        ConnectionEstablishedFinding(
            id=FindingId.CONNECTION_ESTABLISHED,
            severity=Severity.OK,
            confidence="medium",  # type: ignore[arg-type]
            status="passed",  # type: ignore[arg-type]
            title="PostgreSQL connection established",
            scope=_scope(),
            evidence=ConnectionEstablishedEvidence(tls_used=True),
        )


def test_finding_union_round_trip() -> None:
    finding = ConnectionFailedFinding(
        id=FindingId.CONNECTION_FAILED,
        severity=Severity.CRITICAL,
        confidence="high",
        status="triggered",  # type: ignore[arg-type]
        title="Could not connect to PostgreSQL",
        scope=_scope(),
        evidence=ConnectionFailedEvidence(
            category="authentication_failed",
            classification_source=ClassificationSource.SQLSTATE,
            sqlstate="28P01",
        ),
        remediation=Remediation(
            summary="Verify the selected libpq service, role and credential source."
        ),
    )
    adapter = TypeAdapter(Finding)
    parsed = adapter.validate_python(finding.model_dump(mode="python"))
    assert isinstance(parsed, ConnectionFailedFinding)
    assert parsed.id is FindingId.CONNECTION_FAILED


def test_verified_finding_accepts_valid_payload() -> None:
    finding = SessionSafetyVerifiedFinding(
        id=FindingId.CONNECTION_SESSION_SAFETY_VERIFIED,
        severity=Severity.OK,
        confidence="high",
        status="passed",  # type: ignore[arg-type]
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
        limitations=(
            "No write statement was executed by connect-test.",
            "Write enforcement is verified separately by CI safety tests.",
            "Read-only transaction is not a general SQL sandbox.",
        ),
    )
    assert finding.evidence.search_path == ("pg_catalog",)


def test_supported_finding_literal() -> None:
    finding = ServerVersionSupportedFinding(
        id=FindingId.CONNECTION_SERVER_VERSION_SUPPORTED,
        severity=Severity.OK,
        confidence="high",
        status="passed",  # type: ignore[arg-type]
        title="PostgreSQL version is supported",
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
    assert finding.evidence.version_support == "supported"


def test_misconfigured_set_rejected_ok() -> None:
    expected = SessionSafetyExpectedState(
        default_transaction_read_only=True,
        transaction_read_only=True,
        statement_timeout_ms=15000,
        lock_timeout_ms=2000,
        idle_in_transaction_session_timeout_ms=15000,
        search_path=("pg_catalog",),
    )
    evidence = SessionSafetyMisconfiguredEvidence(
        category=SessionSafetyMisconfigurationCategory.SET_REJECTED,
        expected=expected,
        observed=None,
        sqlstate="42501",
    )
    finding = SessionSafetyMisconfiguredFinding(
        id=FindingId.CONNECTION_SESSION_SAFETY_MISCONFIGURED,
        severity=Severity.CRITICAL,
        confidence="high",
        status="triggered",  # type: ignore[arg-type]
        title="Diagnostic session safety settings are not active",
        scope=_scope(),
        evidence=evidence,
    )
    assert finding.evidence.observed is None
