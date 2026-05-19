from __future__ import annotations

import unittest
from datetime import datetime, timezone

from core.edge import build_recommendation
from core.markets import MarketSnapshot, market_mid_probability
from core.risk import fractional_kelly


class MarketEdgeTests(unittest.TestCase):
    def test_mid_probability_uses_bid_ask(self) -> None:
        snapshot = MarketSnapshot("m1", "YES", datetime.now(timezone.utc), 0.42, 0.46)

        self.assertAlmostEqual(market_mid_probability(snapshot), 0.44)

    def test_fractional_kelly_caps_bet_size(self) -> None:
        size = fractional_kelly(model_prob=0.62, market_prob=0.50, fraction=0.5, cap=0.04)

        self.assertEqual(size, 0.04)

    def test_recommendation_passes_when_edge_and_size_clear(self) -> None:
        snapshot = MarketSnapshot("m1", "YES", datetime.now(timezone.utc), 0.40, 0.42)

        recommendation = build_recommendation(snapshot, model_prob=0.50, min_edge=0.03)

        self.assertTrue(recommendation.passes_filter)
        self.assertGreater(recommendation.bankroll_fraction, 0)


if __name__ == "__main__":
    unittest.main()

