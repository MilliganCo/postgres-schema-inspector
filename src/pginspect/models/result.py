"""CommandResult discriminated union (schema 1.0)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_serializer, model_validator

from pginspect.models.base import PublicModel
from pginspect.models.context import ConnectionContext
from pginspect.models.enums import CommandExitCode, CommandOutcome
from pginspect.models.execution_error import ExecutionError
from pginspect.models.finding import Finding
from pginspect.exit_codes import resolve_completed_exit_code, resolve_failed_exit_code


class CommandResultBase(PublicModel):
    schema_version: Literal["1.0"] = "1.0"
    started_at: datetime
    duration_ms: Annotated[int, Field(ge=0)]
    app_version: str

    @field_serializer("started_at")
    def serialize_started_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


class VersionCommandResult(CommandResultBase):
    command: Literal["version"] = "version"
    outcome: Literal[CommandOutcome.COMPLETED] = CommandOutcome.COMPLETED
    exit_code: Literal[CommandExitCode.OK] = CommandExitCode.OK
    context: None = None
    findings: tuple[()] = ()
    error: None = None


class ConnectTestCommandResult(CommandResultBase):
    command: Literal["connect-test"] = "connect-test"
    outcome: CommandOutcome
    exit_code: CommandExitCode
    context: ConnectionContext | None
    findings: tuple[Finding, ...]
    error: ExecutionError | None

    @model_validator(mode="after")
    def validate_outcome_invariants(self) -> ConnectTestCommandResult:
        from pginspect.models.enums import FindingId, FindingStatus, Severity
        from pginspect.models.finding import ConnectionFailedFinding

        if self.outcome is CommandOutcome.COMPLETED:
            if self.error is not None:
                raise ValueError("completed outcome requires error=null")
            if self.exit_code not in {
                CommandExitCode.OK,
                CommandExitCode.WARNING,
                CommandExitCode.CRITICAL,
            }:
                raise ValueError("completed outcome requires exit_code in {0,1,2}")
            expected = resolve_completed_exit_code(self.findings)
            if self.exit_code != expected:
                raise ValueError(
                    f"exit_code {int(self.exit_code)} does not match findings contribution {int(expected)}"
                )
        elif self.outcome is CommandOutcome.FAILED:
            if self.error is None:
                raise ValueError("failed outcome requires error")
            if self.exit_code not in {
                CommandExitCode.OPERATIONAL_FAILURE,
                CommandExitCode.INTERNAL_FAILURE,
            }:
                raise ValueError("failed outcome requires exit_code in {3,5}")
            expected = resolve_failed_exit_code(self.error)
            if self.exit_code != expected:
                raise ValueError(
                    f"exit_code {int(self.exit_code)} does not match error category contribution {int(expected)}"
                )

        failed_findings = [f for f in self.findings if isinstance(f, ConnectionFailedFinding)]
        if failed_findings:
            failed = failed_findings[0]
            if len(self.findings) != 1:
                raise ValueError("connection.failed must be the only finding")
            if self.context is not None:
                raise ValueError("connection.failed requires context=null")
            if self.outcome is not CommandOutcome.FAILED:
                raise ValueError("connection.failed requires outcome=failed")
            if self.exit_code is not CommandExitCode.OPERATIONAL_FAILURE:
                raise ValueError("connection.failed requires exit_code=3")
            if self.error is None or self.error.category.value != "connection":
                raise ValueError("connection.failed requires error.category=connection")
            if self.error.code.value != failed.evidence.category:
                raise ValueError("connection.failed evidence.category must match error.code")

        version_ids = {
            FindingId.CONNECTION_SERVER_VERSION_SUPPORTED,
            FindingId.CONNECTION_SERVER_VERSION_EXPERIMENTAL,
            FindingId.CONNECTION_SERVER_VERSION_UNTESTED,
            FindingId.CONNECTION_SERVER_VERSION_UNSUPPORTED,
        }
        version_findings = [f for f in self.findings if f.id in version_ids]
        if version_findings and self.context is None:
            raise ValueError("version finding requires non-null context")
        if self.context is not None:
            safety_ok = any(
                f.id is FindingId.CONNECTION_SESSION_SAFETY_VERIFIED
                and f.status is FindingStatus.PASSED
                for f in self.findings
            )
            if not safety_ok:
                raise ValueError("non-null context requires session_safety_verified")
            if len(version_findings) != 1:
                raise ValueError("non-null context requires exactly one version finding")
            version_finding = version_findings[0]
            version_support = getattr(version_finding.evidence, "version_support", None)
            if version_support != self.context.version_support.value:
                raise ValueError("version finding evidence must match context.version_support")

        # silence unused import warning for Severity in some paths
        _ = Severity
        return self


CommandResult = Annotated[
    VersionCommandResult | ConnectTestCommandResult,
    Field(discriminator="command"),
]

command_result_adapter: TypeAdapter[CommandResult] = TypeAdapter(CommandResult)
