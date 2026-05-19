from __future__ import annotations

from pydantic import BaseModel


class StrategyKpi(BaseModel):
    label: str
    value: str
    hint: str
    kind: str | None = None


class SettledBet(BaseModel):
    when: str
    market: str
    clv: str
    result: str
    kind: str


class StrategyResponse(BaseModel):
    strategy_id: str
    name: str
    version: str
    mode: str
    enabled: bool
    kpis: list[StrategyKpi]
    settled: list[SettledBet]
