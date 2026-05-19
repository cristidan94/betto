from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.cli.main import (
    _backtest_run_id,
    _corpus_snapshot_id,
    _feature_snapshot_id,
    _paper_bet_drawdowns_by_strategy,
    _paper_bet_readiness_payload,
)


class CliFeatureTests(unittest.TestCase):
    def test_feature_snapshot_id_is_stable_for_same_inputs(self) -> None:
        fixtures = [Path("tests/fixtures/cs_match_001.json").resolve()]
        as_of = datetime(2026, 5, 21, tzinfo=timezone.utc)

        first = _feature_snapshot_id(fixtures, as_of)
        second = _feature_snapshot_id(list(reversed(fixtures)), as_of)

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("cs-fixture-features-"))

    def test_feature_snapshot_id_changes_with_as_of(self) -> None:
        fixtures = [Path("tests/fixtures/cs_match_001.json").resolve()]

        first = _feature_snapshot_id(fixtures, datetime(2026, 5, 21, tzinfo=timezone.utc))
        second = _feature_snapshot_id(fixtures, datetime(2026, 5, 22, tzinfo=timezone.utc))

        self.assertNotEqual(first, second)

    def test_backtest_ids_are_stable(self) -> None:
        corpus = Path("tests/fixtures/corpus").resolve()
        snapshot_id = _corpus_snapshot_id(corpus)
        config = {
            "corpus": str(corpus),
            "start": "2026-01-01",
            "end": "2026-03-31",
            "train_days": 30,
            "validate_days": 20,
            "step_days": 15,
        }

        first = _backtest_run_id("cs_baseline_fixture_v1", snapshot_id, config)
        second = _backtest_run_id("cs_baseline_fixture_v1", snapshot_id, dict(reversed(list(config.items()))))

        self.assertTrue(snapshot_id.startswith("cs-fixture-corpus-"))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("cs-backtest-"))

    def test_paper_bet_readiness_payload(self) -> None:
        payload = _paper_bet_readiness_payload(
            {
                "strategy_id": "strategy-1",
                "settled_bets": 3,
                "roi": "0.12",
                "hit_rate": "0.67",
                "mean_clv": "0.03",
                "pnl_usd": "18.5",
            },
            min_settled_bets=2,
            min_roi=0.05,
            min_hit_rate=0.5,
            min_mean_clv=0.0,
            min_pnl_usd=0.0,
            max_drawdown_usd=10.0,
            drawdown_usd=0.0,
        )

        self.assertTrue(payload["passed"])
        check_names = {check["name"] for check in payload["checks"]}  # type: ignore[index]
        self.assertIn("settled_bets", check_names)
        self.assertIn("mean_clv", check_names)
        self.assertIn("max_drawdown_usd", check_names)

    def test_paper_bet_readiness_payload_can_fail(self) -> None:
        payload = _paper_bet_readiness_payload(
            {"strategy_id": "strategy-1", "settled_bets": 0, "roi": None, "hit_rate": None, "mean_clv": None, "pnl_usd": None},
            min_settled_bets=1,
            min_roi=0.0,
            min_hit_rate=0.0,
            min_mean_clv=0.0,
            min_pnl_usd=0.0,
            max_drawdown_usd=0.0,
            drawdown_usd=1.0,
        )

        self.assertFalse(payload["passed"])

    def test_paper_bet_drawdowns_group_by_strategy(self) -> None:
        drawdowns = _paper_bet_drawdowns_by_strategy(
            [
                {"strategy_id": "a", "placed_at": "2026-01-01", "pnl_usd": 10},
                {"strategy_id": "a", "placed_at": "2026-01-02", "pnl_usd": -4},
                {"strategy_id": "a", "placed_at": "2026-01-03", "pnl_usd": 2},
                {"strategy_id": "b", "placed_at": "2026-01-01", "pnl_usd": -3},
            ]
        )

        self.assertEqual(drawdowns["a"], 4.0)
        self.assertEqual(drawdowns["b"], 3.0)


if __name__ == "__main__":
    unittest.main()
