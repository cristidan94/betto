from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.markets.models import MarketSnapshot
from core.markets.probability import edge, market_mid_probability
from core.risk.kelly import fractional_kelly


@dataclass(frozen=True)
class Recommendation:
    market_id: str
    outcome: str
    taken_at: datetime
    model_prob: float
    market_prob: float
    edge: float
    bankroll_fraction: float
    passes_filter: bool
    reason: str


def build_recommendation(
    snapshot: MarketSnapshot,
    model_prob: float,
    min_edge: float,
    kelly_fraction: float = 0.25,
    bankroll_cap: float = 0.04,
) -> Recommendation:
    market_prob = market_mid_probability(snapshot)
    computed_edge = edge(model_prob, market_prob)
    bankroll_fraction = fractional_kelly(model_prob, market_prob, kelly_fraction, bankroll_cap)
    passes = computed_edge >= min_edge and bankroll_fraction > 0
    reason = "edge_pass" if passes else "edge_or_size_below_threshold"
    return Recommendation(
        market_id=snapshot.market_id,
        outcome=snapshot.outcome,
        taken_at=snapshot.taken_at,
        model_prob=model_prob,
        market_prob=market_prob,
        edge=computed_edge,
        bankroll_fraction=bankroll_fraction,
        passes_filter=passes,
        reason=reason,
    )

