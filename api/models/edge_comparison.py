from __future__ import annotations

from pydantic import BaseModel


class SourceOddsEntry(BaseModel):
    source: str
    prob: float
    best_bid: float | None = None
    best_ask: float | None = None
    bookmaker: str | None = None


class EdgeComparisonEntry(BaseModel):
    contest_id: str
    match: str
    market_type: str
    outcome: str
    model_prob: float | None = None
    polymarket_prob: float | None = None
    polymarket_volume: float | None = None
    oddspapi_prob: float | None = None
    oddspapi_bookmaker: str | None = None
    edge_vs_polymarket: float | None = None
    edge_vs_oddspapi: float | None = None
    edge_diff: float | None = None
    sources: list[SourceOddsEntry] = []


class EdgeComparisonResponse(BaseModel):
    date: str
    comparisons: list[EdgeComparisonEntry]
    markets_with_both_sources: int
    total_markets: int
