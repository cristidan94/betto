from __future__ import annotations

from pydantic import BaseModel


class MatchEntry(BaseModel):
    id: str
    label: str
    tier: str
    format: str
    start: str
    start_date: str
    start_in: str
    regime: str
    veto: str
    open_markets: int
    recommendations: int
    exposure_pct: float
    best_edge: float


class MatchesResponse(BaseModel):
    date: str
    matches: list[MatchEntry]


class MarketEntry(BaseModel):
    market: str
    edge: float
    size: float
    state: str


class MatchMarketsResponse(BaseModel):
    match_id: str
    markets: list[MarketEntry]
