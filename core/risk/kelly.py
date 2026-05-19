from __future__ import annotations


def fractional_kelly(model_prob: float, market_prob: float, fraction: float = 0.25, cap: float = 0.04) -> float:
    """Return bankroll fraction for a binary bet priced as a probability."""

    if not 0 < market_prob < 1:
        raise ValueError("market_prob must be between 0 and 1, exclusive")
    if not 0 <= model_prob <= 1:
        raise ValueError("model_prob must be between 0 and 1")
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    if not 0 < cap <= 1:
        raise ValueError("cap must be in (0, 1]")

    decimal_odds = 1 / market_prob
    net_odds = decimal_odds - 1
    full_kelly = (net_odds * model_prob - (1 - model_prob)) / net_odds
    return max(0.0, min(full_kelly * fraction, cap))

