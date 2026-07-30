from __future__ import annotations

import math

import pytest
from pydantic import TypeAdapter, ValidationError

from pginspect.impact.models.scalars import JSONScalar

_adapter: TypeAdapter[JSONScalar] = TypeAdapter(JSONScalar)


@pytest.mark.parametrize("value", ["text", 1, 1.5, True, False, None])
def test_json_scalar_accepts_flat_python_scalars(value: object) -> None:
    assert _adapter.validate_python(value) == value


@pytest.mark.parametrize("value", [{"a": 1}, [1, 2], {1, 2}])
def test_json_scalar_rejects_nested_structures(value: object) -> None:
    with pytest.raises(ValidationError):
        _adapter.validate_python(value)


def test_json_scalar_rejects_nan_and_inf_in_evidence_attributes() -> None:
    from pginspect.impact.models.evidence import ImpactEvidence

    with pytest.raises(ValidationError):
        ImpactEvidence(
            evidence_id="e1",
            kind="server_fact",
            summary="s",
            attributes={"x": math.nan},
        )
    with pytest.raises(ValidationError):
        ImpactEvidence(
            evidence_id="e1",
            kind="server_fact",
            summary="s",
            attributes={"x": math.inf},
        )
