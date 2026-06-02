from __future__ import annotations

import unittest
from datetime import datetime, timezone

from core.edge import Recommendation
from core.execution import BetMode, ExecutionService
from core.markets import MarketSnapshot


def _make_recommendation(passes: bool = True, edge: float = 0.05, bankroll_fraction: float = 0.02) -> Recommendation:
    return Recommendation(
        market_id="pm-1",
        outcome="NAVI",
        taken_at=datetime.now(timezone.utc),
        model_prob=0.60,
        market_prob=0.55,
        edge=edge,
        bankroll_fraction=bankroll_fraction,
        passes_filter=passes,
        reason="edge_pass" if passes else "edge_or_size_below_threshold",
    )


def _make_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        market_id="pm-1",
        outcome="NAVI",
        taken_at=datetime.now(timezone.utc),
        best_bid=0.54,
        best_ask=0.56,
        last_trade_price=0.55,
        depth_bid_1pct=100.0,
        depth_ask_1pct=50.0,
    )


class ExecutionServiceTests(unittest.TestCase):
    def test_paper_execution_succeeds(self) -> None:
        svc = ExecutionService(mode=BetMode.PAPER, bankroll_usd=10000.0)
        result = svc.execute_recommendation(_make_recommendation(), _make_snapshot())
        self.assertTrue(result.success)
        self.assertEqual(result.mode, BetMode.PAPER)
        self.assertAlmostEqual(result.size_usd, 200.0)
        self.assertAlmostEqual(result.fill_price, 0.55)
        self.assertTrue(result.order_id.startswith("paper-"))

    def test_rejects_failing_recommendation(self) -> None:
        svc = ExecutionService(mode=BetMode.PAPER, bankroll_usd=10000.0)
        result = svc.execute_recommendation(_make_recommendation(passes=False), _make_snapshot())
        self.assertFalse(result.success)
        self.assertIn("does not pass filter", result.error)

    def test_daily_cap_enforced(self) -> None:
        svc = ExecutionService(mode=BetMode.PAPER, bankroll_usd=1000.0, daily_cap_fraction=0.05)
        rec = _make_recommendation(bankroll_fraction=0.04)
        snap = _make_snapshot()

        result1 = svc.execute_recommendation(rec, snap)
        self.assertTrue(result1.success)

        result2 = svc.execute_recommendation(rec, snap)
        self.assertFalse(result2.success)
        self.assertIn("daily cap exceeded", result2.error)

    def test_live_mode_without_client_fails(self) -> None:
        svc = ExecutionService(mode=BetMode.LIVE, bankroll_usd=10000.0)
        result = svc.execute_recommendation(_make_recommendation(), _make_snapshot())
        self.assertFalse(result.success)
        self.assertIn("no order client", result.error)

    def test_live_mode_without_token_fails(self) -> None:
        svc = ExecutionService(mode=BetMode.LIVE, bankroll_usd=10000.0, order_client=object())
        result = svc.execute_recommendation(_make_recommendation(), _make_snapshot())
        self.assertFalse(result.success)
        self.assertIn("token_id required", result.error)

    def test_single_bet_cap(self) -> None:
        svc = ExecutionService(mode=BetMode.PAPER, bankroll_usd=10000.0, max_single_bet_fraction=0.01)
        result = svc.execute_recommendation(
            _make_recommendation(bankroll_fraction=0.04), _make_snapshot(),
        )
        self.assertTrue(result.success)
        self.assertAlmostEqual(result.size_usd, 100.0)


if __name__ == "__main__":
    unittest.main()
