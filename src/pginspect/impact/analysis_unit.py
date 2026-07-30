"""`AnalysisUnit`: the pre-card resolved-statement shape (design section 0.1).

Introduced in Task 5 so `resolve.py` has a stable target/payload shape to
populate. `apply_sequence_constraints` (Task 6, `sequence.py`) consumes and
re-marks these units; this module only defines the shape and carries no
sequencing logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pginspect.impact.models.enums import AnalysisStatus
from pginspect.impact.parser.ast import SourceSpan

AnalysisUnitFamily = Literal["type", "add", "drop", "unsupported_parser"]

__all__ = ["AnalysisUnitFamily", "AnalysisUnit", "SourceSpan"]


@dataclass(frozen=True)
class AnalysisUnit:
    statement_index: int
    source_span: SourceSpan
    statement_fingerprint: str
    sanitized_preview: str
    family: AnalysisUnitFamily
    ast: object
    analysis_status: AnalysisStatus
    table_oid: int | None
    table_schema: str | None
    table_name: str | None
    column_attnum: int | None
    column_normalized_name: str | None
    resolution_payload: object | None
    evidence_ids: tuple[str, ...]
    requires_virtual_schema_state: bool
    limitations: tuple[str, ...]
