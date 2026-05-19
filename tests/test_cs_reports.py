from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sports.cs.reports import build_baseline_strategy_report, compact_strategy_report, write_strategy_report


class CsReportsTests(unittest.TestCase):
    def test_build_baseline_strategy_report(self) -> None:
        report = build_baseline_strategy_report(
            Path("tests/fixtures/corpus"),
            Path("tests/fixtures/market_corpus"),
            min_edge=0.03,
        )

        self.assertEqual(report["strategy_id"], "cs_baseline_fixture_v1")
        self.assertIn("model", report)
        self.assertIn("paper", report)
        self.assertTrue(report["readiness"]["passed"])  # type: ignore[index]
        check_names = {check["name"] for check in report["readiness"]["checks"]}  # type: ignore[index]
        self.assertIn("total_bankroll_fraction", check_names)
        self.assertIn("max_drawdown_per_unit_stake", check_names)

    def test_write_strategy_report(self) -> None:
        report = build_baseline_strategy_report(
            Path("tests/fixtures/cs_match_001.json"),
            Path("tests/fixtures/cs_market_prices.json"),
            min_edge=0.03,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = write_strategy_report(report, Path(tmp))

            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["strategy_id"], "cs_baseline_fixture_v1")
            self.assertIn("readiness", payload)
            self.assertTrue(path.name.startswith("cs-baseline-strategy-report-"))

    def test_build_baseline_strategy_report_can_fail_readiness(self) -> None:
        report = build_baseline_strategy_report(
            Path("tests/fixtures/corpus"),
            Path("tests/fixtures/market_corpus"),
            min_edge=0.03,
            max_brier_score=0.01,
        )

        self.assertFalse(report["readiness"]["passed"])  # type: ignore[index]

    def test_build_baseline_strategy_report_can_fail_risk_readiness(self) -> None:
        report = build_baseline_strategy_report(
            Path("tests/fixtures/corpus"),
            Path("tests/fixtures/market_corpus"),
            min_edge=0.03,
            max_total_bankroll_fraction=0.01,
        )

        self.assertFalse(report["readiness"]["passed"])  # type: ignore[index]
        failed = [check for check in report["readiness"]["checks"] if not check["passed"]]  # type: ignore[index]
        self.assertEqual(failed[0]["name"], "total_bankroll_fraction")

    def test_build_baseline_strategy_report_applies_paper_risk_caps(self) -> None:
        report = build_baseline_strategy_report(
            Path("tests/fixtures/cs_match_001.json"),
            Path("tests/fixtures/cs_market_prices.json"),
            min_edge=0.03,
            market_bankroll_cap=0.01,
            max_daily_bankroll_fraction=0.015,
        )

        paper = report["paper"]  # type: ignore[assignment]

        self.assertEqual(paper["recommendations"], 1)  # type: ignore[index]
        self.assertEqual(paper["reason_counts"]["daily_cap_reached"], 1)  # type: ignore[index]
        self.assertLessEqual(paper["total_bankroll_fraction"], 0.015)  # type: ignore[index]

    def test_compact_strategy_report_removes_recommendation_rows(self) -> None:
        report = build_baseline_strategy_report(
            Path("tests/fixtures/corpus"),
            Path("tests/fixtures/market_corpus"),
            min_edge=0.03,
        )

        compact = compact_strategy_report(report)

        self.assertNotIn("results", compact["paper"])  # type: ignore[operator]
        self.assertIn("readiness", compact)


if __name__ == "__main__":
    unittest.main()
