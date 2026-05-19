from __future__ import annotations

from pydantic import BaseModel


class RiskKpi(BaseModel):
    label: str
    value: str
    hint: str
    kind: str | None = None


class CapitalBucket(BaseModel):
    name: str
    used: float
    cap: float
    state: str
    kind: str


class RiskCap(BaseModel):
    label: str
    value: str
    hint: str


class KillSwitch(BaseModel):
    name: str
    state: str
    trigger: str
    kind: str


class RiskResponse(BaseModel):
    kpis: list[RiskKpi]
    buckets: list[CapitalBucket]
    caps: list[RiskCap]
    kill_switches: list[KillSwitch]
