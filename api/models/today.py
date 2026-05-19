from __future__ import annotations

from pydantic import BaseModel


class Correlation(BaseModel):
    used: float
    cap: float


class TodayRecommendation(BaseModel):
    id: str
    match: str
    market: str
    model_prob: float
    market_prob: float
    edge: float
    size: float
    confidence: str
    strategy: str
    close: str
    veto: str
    correlation: Correlation
    seed: int


class TodaySummary(BaseModel):
    date: str
    surfaced: int
    above_filter: int
    would_stake_usd: float
    exposure_pct: float
    exposure_cap_pct: float


class TodayResponse(BaseModel):
    summary: TodaySummary
    recommendations: list[TodayRecommendation]
