"""Impact evidence contracts (schema 0.1, design section 4.3)."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import Field

from pginspect.impact.models.enums import EvidenceKind
from pginspect.impact.models.scalars import JSONScalar
from pginspect.models.base import PublicModel


class ImpactEvidence(PublicModel):
    evidence_id: str
    kind: EvidenceKind
    summary: str
    attributes: Mapping[str, JSONScalar] = Field(default_factory=dict)
