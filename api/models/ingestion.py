from __future__ import annotations

from typing import Any

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


class IngestionJobRequest(BaseModel):
    action: str
    limit: int = 100
    max_pages: int = 5
    include_closed: bool = True
    closed_only: bool = False
    include_trades: bool = True
    timeout_sec: int = 300


class IngestionJobStep(BaseModel):
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    summary: Any | None = None


class IngestionJobResponse(BaseModel):
    action: str
    ok: bool
    steps: list[IngestionJobStep]
