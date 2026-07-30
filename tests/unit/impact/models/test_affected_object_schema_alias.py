"""AffectedObjectRef must serialize the wire key `schema`, never `schema_`."""

from __future__ import annotations

from pginspect.impact.models.card import AffectedObjectRef
from pginspect.impact.models.enums import ImpactRole, ObjectKind


def _sample_ref() -> AffectedObjectRef:
    return AffectedObjectRef(
        object_kind=ObjectKind.TABLE,
        identity="public.t",
        schema_="public",
        name="t",
        parent_identity=None,
        impact_role=ImpactRole.TARGET,
        detail=None,
    )


def test_model_dump_by_alias_uses_schema_key() -> None:
    dumped = _sample_ref().model_dump(by_alias=True)
    assert "schema" in dumped
    assert "schema_" not in dumped
    assert dumped["schema"] == "public"


def test_model_dump_json_mode_by_alias_uses_schema_key() -> None:
    dumped = _sample_ref().model_dump(mode="json", by_alias=True)
    assert "schema" in dumped
    assert "schema_" not in dumped
    assert dumped["schema"] == "public"


def test_accepts_construction_via_alias() -> None:
    ref = AffectedObjectRef(
        object_kind=ObjectKind.TABLE,
        identity="public.t",
        schema="public",  # type: ignore[call-arg]
        name="t",
        parent_identity=None,
        impact_role=ImpactRole.TARGET,
        detail=None,
    )
    assert ref.schema_ == "public"


def test_accepts_construction_via_field_name() -> None:
    ref = _sample_ref()
    assert ref.schema_ == "public"


def test_null_schema_serializes_with_alias_key() -> None:
    ref = AffectedObjectRef(
        object_kind=ObjectKind.FUNCTION,
        identity="pg_catalog.now()",
        schema_=None,
        name="now",
        parent_identity=None,
        impact_role=ImpactRole.RELATED,
        detail=None,
    )
    dumped = ref.model_dump(by_alias=True)
    assert "schema" in dumped
    assert dumped["schema"] is None
