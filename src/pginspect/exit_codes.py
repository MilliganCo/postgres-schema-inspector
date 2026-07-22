"""Exit-code resolution for completed and failed CommandResults."""

from __future__ import annotations

from pginspect.models.enums import CommandExitCode, ExecutionErrorCategory, FindingStatus, Severity
from pginspect.models.execution_error import ExecutionError
from pginspect.models.finding import Finding

_FINDING_EXIT_CONTRIBUTION: dict[Severity, CommandExitCode] = {
    Severity.CRITICAL: CommandExitCode.CRITICAL,
    Severity.WARNING: CommandExitCode.WARNING,
    Severity.OK: CommandExitCode.OK,
}


def resolve_completed_exit_code(findings: tuple[Finding, ...]) -> CommandExitCode:
    contributions = (
        _FINDING_EXIT_CONTRIBUTION[finding.severity]
        if finding.status is FindingStatus.TRIGGERED
        else CommandExitCode.OK
        for finding in findings
    )
    return CommandExitCode(
        max((int(code) for code in contributions), default=int(CommandExitCode.OK))
    )


def resolve_failed_exit_code(error: ExecutionError) -> CommandExitCode:
    match error.category:
        case ExecutionErrorCategory.INTERNAL:
            return CommandExitCode.INTERNAL_FAILURE
        case (
            ExecutionErrorCategory.CONNECTION
            | ExecutionErrorCategory.SESSION
            | ExecutionErrorCategory.OPERATIONAL
        ):
            return CommandExitCode.OPERATIONAL_FAILURE
    raise ValueError(f"Unsupported execution error category: {error.category!r}")
