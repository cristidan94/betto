from __future__ import annotations

from pydantic import BaseModel


class BetLogSummary(BaseModel):
    bets: int
    settled_bets: int
    open_bets: int
    stake_usd: float
    pnl_usd: float
    roi: float
    mean_clv: float
    hit_rate: float


class BetLogRow(BaseModel):
    timestamp: str
    id: str
    market: str
    model_market: str
    edge: float
    size: float
    stake_usd: float
    mode: str
    state: str
    result: str
    clv: float | None
    strategy: str


class BetLogResponse(BaseModel):
    summary: BetLogSummary
    rows: list[BetLogRow]
