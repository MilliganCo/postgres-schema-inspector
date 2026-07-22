"""Domain exceptions for control flow (never serialize raw driver exceptions)."""

from __future__ import annotations

from pginspect.models.enums import (
    ClassificationSource,
    ExecutionErrorCode,
    SessionSafetyMisconfigurationCategory,
)
from pginspect.models.execution_error import DebugFrame
from pginspect.models.finding import SessionSafetyExpectedState, SessionSafetyObservedState


class PginspectError(Exception):
    """Base package domain error."""


class PginspectConfigurationError(PginspectError):
    """Invalid configuration that must not attempt a connection."""

    def __init__(self, public_message: str) -> None:
        self.public_message = public_message
        super().__init__(public_message)


class PginspectConnectError(PginspectError):
    """Expected connect-time failure mapped from Psycopg/libpq signals."""

    def __init__(
        self,
        *,
        code: ExecutionErrorCode,
        classification_source: ClassificationSource,
        sqlstate: str | None = None,
        driver_exception_type: str = "",
        debug_frames: tuple[DebugFrame, ...] = (),
    ) -> None:
        self.code = code
        self.classification_source = classification_source
        self.sqlstate = sqlstate
        self.driver_exception_type = driver_exception_type
        self.debug_frames = debug_frames
        super().__init__(code.value)


class ConnectAuthenticationError(PginspectConnectError):
    pass


class ConnectNetworkError(PginspectConnectError):
    pass


class ConnectTimeoutError(PginspectConnectError):
    pass


class ConnectTlsError(PginspectConnectError):
    pass


class ConnectDatabaseMissingError(PginspectConnectError):
    pass


class ConnectFailedError(PginspectConnectError):
    pass


class SessionSafetyError(PginspectError):
    """Required session safety GUCs were rejected or did not match expectations."""

    def __init__(
        self,
        *,
        category: SessionSafetyMisconfigurationCategory,
        expected: SessionSafetyExpectedState,
        observed: SessionSafetyObservedState | None,
        sqlstate: str | None = None,
        debug_frames: tuple[DebugFrame, ...] = (),
    ) -> None:
        self.category = category
        self.expected = expected
        self.observed = observed
        self.sqlstate = sqlstate
        self.debug_frames = debug_frames
        super().__init__(category.value)


class PginspectInternalError(PginspectError):
    """Invariant / programming failure (maps to exit 5)."""

    def __init__(
        self,
        message: str = "internal_failure",
        *,
        debug_frames: tuple[DebugFrame, ...] = (),
        driver_exception_type: str = "",
    ) -> None:
        self.debug_frames = debug_frames
        self.driver_exception_type = driver_exception_type
        super().__init__(message)
