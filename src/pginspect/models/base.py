"""Shared Pydantic base for public Foundation models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PublicModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )
