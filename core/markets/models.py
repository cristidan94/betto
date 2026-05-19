from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Market:
    market_id: str
    source: str
    question: str
    market_type: str
    contest_id: str | None
    outcomes: tuple[str, ...]
    created_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_outcome: str | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    market_id: str
    outcome: str
    taken_at: datetime
    best_bid: float | None
    best_ask: float | None
    last_trade_price: float | None = None
    depth_bid_1pct: float | None = None
    depth_ask_1pct: float | None = None

