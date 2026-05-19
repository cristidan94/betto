from __future__ import annotations

from core.markets.models import MarketSnapshot


def market_mid_probability(snapshot: MarketSnapshot) -> float:
    """Return a usable market probability from bid/ask or last trade price."""

    if snapshot.best_bid is not None and snapshot.best_ask is not None:
        if snapshot.best_bid > snapshot.best_ask:
            raise ValueError("best_bid cannot be greater than best_ask")
        return (snapshot.best_bid + snapshot.best_ask) / 2
    if snapshot.last_trade_price is not None:
        return snapshot.last_trade_price
    raise ValueError("snapshot has no bid/ask or last trade price")


def edge(model_prob: float, market_prob: float) -> float:
    if not 0 <= model_prob <= 1:
        raise ValueError("model_prob must be between 0 and 1")
    if not 0 <= market_prob <= 1:
        raise ValueError("market_prob must be between 0 and 1")
    return model_prob - market_prob

