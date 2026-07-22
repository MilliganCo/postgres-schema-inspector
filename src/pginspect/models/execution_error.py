"""Serializable execution error models."""

from __future__ import annotations

from pginspect.models.base import PublicModel
from pginspect.models.enums import (
    ClassificationSource,
    ExecutionErrorCategory,
    ExecutionErrorCode,
)


class DebugFrame(PublicModel):
    module: str
    function: str
    line: int


class DebugPayload(PublicModel):
    exception_type: str
    causal_chain_types: tuple[str, ...] = ()
    frames: tuple[DebugFrame, ...] = ()


class ExecutionError(PublicModel):
    code: ExecutionErrorCode
    category: ExecutionErrorCategory
    message: str
    retryable: bool
    sqlstate: str | None = None
    classification_source: ClassificationSource | None = None
    debug: DebugPayload | None = None
