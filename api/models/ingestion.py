from __future__ import annotations

from pydantic import BaseModel


class IngestionSource(BaseModel):
    name: str
    kind: str
    fresh: str
    target: str
    cadence: str
    rows: int
    last_error: str
    on: bool


class FeatureFreshness(BaseModel):
    name: str
    fresh: str
    kind: str
    rows: int


class IngestionResponse(BaseModel):
    sources: list[IngestionSource]
    features: list[FeatureFreshness]
    snapshot_lag: str
    snapshot_count: int
    schemas_ok: bool
    leakage_tests_ok: bool
