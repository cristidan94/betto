from __future__ import annotations

import unittest
from datetime import datetime, timezone

from core.markets import MarketSnapshot, build_comparison


class CrossSourceTests(unittest.TestCase):
    def test_build_comparison_with_two_sources(self) -> None:
        pm_snap = MarketSnapshot(
            market_id="pm-1", outcome="NAVI", taken_at=datetime.now(timezone.utc),
            best_bid=0.60, best_ask=0.64, last_trade_price=0.62,
            depth_bid_1pct=100.0, depth_ask_1pct=50.0,
        )
        odds_snap = MarketSnapshot(
            market_id="odds-1", outcome="NAVI", taken_at=datetime.now(timezone.utc),
            best_bid=0.55, best_ask=0.57, last_trade_price=0.56,
            depth_bid_1pct=None, depth_ask_1pct=None,
        )
        row = build_comparison(
            contest_id="contest-1",
            match_label="NAVI vs Vitality",
            market_type="match_winner",
            outcome="NAVI",
            model_prob=0.65,
            snapshots_by_source={"polymarket": pm_snap, "oddspapi": odds_snap},
            bookmaker_names={"oddspapi": "Pinnacle"},
        )

        self.assertEqual(len(row.sources), 2)
        self.assertAlmostEqual(row.sources[0].prob, 0.62)
        self.assertAlmostEqual(row.sources[1].prob, 0.56)
        self.assertAlmostEqual(row.edge_for_source("polymarket"), 0.03)
        self.assertAlmostEqual(row.edge_for_source("oddspapi"), 0.09)
        self.assertAlmostEqual(row.edge_diff, -0.06)

    def test_best_and_worst_source(self) -> None:
        pm_snap = MarketSnapshot(
            market_id="pm-1", outcome="NAVI", taken_at=datetime.now(timezone.utc),
            best_bid=0.60, best_ask=0.64, last_trade_price=None,
            depth_bid_1pct=None, depth_ask_1pct=None,
        )
        odds_snap = MarketSnapshot(
            market_id="odds-1", outcome="NAVI", taken_at=datetime.now(timezone.utc),
            best_bid=0.55, best_ask=0.57, last_trade_price=None,
            depth_bid_1pct=None, depth_ask_1pct=None,
        )
        row = build_comparison(
            contest_id="contest-1",
            match_label="NAVI vs Vitality",
            market_type="match_winner",
            outcome="NAVI",
            model_prob=None,
            snapshots_by_source={"polymarket": pm_snap, "oddspapi": odds_snap},
        )

        self.assertEqual(row.best_source.source, "polymarket")
        self.assertEqual(row.worst_source.source, "oddspapi")
        self.assertIsNone(row.edge_diff)


if __name__ == "__main__":
    unittest.main()
