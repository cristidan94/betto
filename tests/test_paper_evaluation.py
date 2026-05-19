from __future__ import annotations

import unittest
from pathlib import Path
from datetime import datetime, timezone

from sports.cs.fixtures import load_fixture_corpus
from sports.cs.markets import (
    CsMarketPriceFixture,
    accepted_paper_recommendations_digest,
    accepted_paper_recommendations_payload,
    load_market_price_corpus,
    load_market_price_fixtures,
    compact_paper_evaluation_payload,
    paper_evaluate_baseline,
    paper_evaluation_payload,
    write_accepted_paper_recommendations_artifact,
    write_accepted_paper_recommendations_csv,
    write_paper_evaluation_artifact,
    write_paper_recommendations_csv,
)
import json
import tempfile


class PaperEvaluationTests(unittest.TestCase):
    def test_load_market_price_fixtures(self) -> None:
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        self.assertEqual(len(prices), 4)
        self.assertEqual(prices[0].team_id, "cs:participant:hltv:4608")
        self.assertEqual(prices[0].close_price, 0.52)
        self.assertEqual(prices[0].resolved_team_hltv_id, "4608")

    def test_load_market_price_corpus_from_directory(self) -> None:
        prices = load_market_price_corpus(Path("tests/fixtures/market_corpus"))

        self.assertEqual(len(prices), 12)

    def test_paper_evaluate_baseline_builds_recommendations(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03)

        self.assertEqual(summary.candidates, 4)
        self.assertEqual(summary.recommendations, 2)
        self.assertIsNotNone(summary.mean_edge)
        self.assertIsNotNone(summary.mean_clv)
        self.assertIsNotNone(summary.roi_per_unit_stake)
        self.assertGreater(summary.total_bankroll_fraction, 0)
        self.assertIsNotNone(summary.max_bankroll_fraction)
        self.assertEqual(summary.max_drawdown_per_unit_stake, 0.0)
        self.assertEqual(summary.reason_counts["edge_pass"], 2)
        self.assertIn("2026-05-20", summary.daily_exposure)
        self.assertIn("2370001", summary.per_match_exposure)
        self.assertGreater(summary.pnl_per_unit_stake, 0)

    def test_paper_evaluation_payload_is_json_ready(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        payload = paper_evaluation_payload(paper_evaluate_baseline(matches, prices, min_edge=0.03))

        self.assertEqual(payload["candidates"], 4)
        self.assertIn("mean_clv", payload)
        self.assertIn("roi_per_unit_stake", payload)
        self.assertIn("max_drawdown_per_unit_stake", payload)
        self.assertIn("total_bankroll_fraction", payload)
        self.assertIn("reason_counts", payload)
        self.assertIn("daily_exposure", payload)
        self.assertIn("per_match_exposure", payload)
        self.assertIn("results", payload)
        self.assertIn("features", payload["results"][0])  # type: ignore[index]
        self.assertIn("score_breakdown", payload["results"][0])  # type: ignore[index]

    def test_compact_paper_evaluation_payload_removes_rows(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        payload = compact_paper_evaluation_payload(paper_evaluate_baseline(matches, prices, min_edge=0.03))

        self.assertNotIn("results", payload)
        self.assertEqual(payload["candidates"], 4)

    def test_accepted_paper_recommendations_payload_filters_rejected_candidates(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        payload = accepted_paper_recommendations_payload(paper_evaluate_baseline(matches, prices, min_edge=0.03))

        self.assertIn("summary", payload)
        self.assertEqual(payload["summary"]["candidates"], 4)  # type: ignore[index]
        self.assertEqual(len(payload["recommendations"]), 2)  # type: ignore[arg-type]
        self.assertTrue(all(row["recommendation"]["passes_filter"] for row in payload["recommendations"]))  # type: ignore[index]
        self.assertIn("best_of", payload["recommendations"][0]["features"])  # type: ignore[index]
        self.assertIn("map_strength_logit", payload["recommendations"][0]["score_breakdown"])  # type: ignore[index]
        self.assertEqual(payload["recommendations"][0]["review_rank"], 1)  # type: ignore[index]
        self.assertEqual(payload["recommendations"][0]["map_index"], 2)  # type: ignore[index]
        self.assertGreater(payload["recommendations"][0]["action_score"], payload["recommendations"][1]["action_score"])  # type: ignore[index]

    def test_accepted_paper_recommendations_payload_can_limit_output(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        payload = accepted_paper_recommendations_payload(paper_evaluate_baseline(matches, prices, min_edge=0.03), max_items=1)

        self.assertEqual(payload["summary"]["recommendations"], 2)  # type: ignore[index]
        self.assertEqual(len(payload["recommendations"]), 1)  # type: ignore[arg-type]
        self.assertEqual(payload["recommendations"][0]["review_rank"], 1)  # type: ignore[index]

    def test_accepted_paper_recommendations_digest_is_compact_and_ranked(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        payload = accepted_paper_recommendations_digest(paper_evaluate_baseline(matches, prices, min_edge=0.03), max_items=1)

        self.assertEqual(payload["summary"]["recommendations"], 2)  # type: ignore[index]
        self.assertEqual(len(payload["recommendations"]), 1)  # type: ignore[arg-type]
        row = payload["recommendations"][0]  # type: ignore[index]
        self.assertEqual(row["review_rank"], 1)
        self.assertIn("edge", row)
        self.assertNotIn("features", row)

    def test_paper_evaluate_baseline_over_corpus(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/corpus"))
        prices = load_market_price_corpus(Path("tests/fixtures/market_corpus"))

        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03)

        self.assertEqual(summary.candidates, 12)
        self.assertGreater(summary.recommendations, 0)

    def test_paper_evaluate_baseline_filters_low_liquidity(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03, min_liquidity_usd=1000)

        self.assertEqual(summary.recommendations, 1)
        blocked = [result for result in summary.results if result.recommendation.reason == "liquidity_below_threshold"]
        self.assertEqual(len(blocked), 1)

    def test_paper_evaluate_baseline_flags_settlement_mismatch(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices_mismatch.json"))

        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03)

        self.assertEqual(summary.recommendations, 0)
        self.assertTrue(summary.results[0].settlement_mismatch)
        self.assertEqual(summary.results[0].recommendation.reason, "settlement_mismatch")

    def test_paper_evaluate_baseline_applies_per_match_cap(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03, max_recommendations_per_match=1)

        self.assertEqual(summary.recommendations, 1)
        capped = [result for result in summary.results if result.recommendation.reason == "per_match_cap_reached"]
        self.assertEqual(len(capped), 1)

    def test_paper_evaluate_baseline_applies_market_bankroll_cap(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03, market_bankroll_cap=0.01)

        self.assertEqual(summary.recommendations, 2)
        self.assertEqual(summary.max_bankroll_fraction, 0.01)
        self.assertAlmostEqual(summary.total_bankroll_fraction, 0.02)

    def test_paper_evaluate_baseline_applies_daily_bankroll_cap(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03, max_daily_bankroll_fraction=0.05)

        self.assertEqual(summary.recommendations, 1)
        capped = [result for result in summary.results if result.recommendation.reason == "daily_cap_reached"]
        self.assertEqual(len(capped), 1)
        self.assertLessEqual(summary.total_bankroll_fraction, 0.05)

    def test_paper_evaluate_baseline_rejects_invalid_controls(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))

        invalid_cases = [
            {"min_edge": -0.01, "min_liquidity_usd": 0.0},
            {"min_liquidity_usd": -1},
            {"max_recommendations_per_match": 0},
            {"market_bankroll_cap": 0},
            {"max_daily_bankroll_fraction": 0},
        ]

        for kwargs in invalid_cases:
            controls = {"min_edge": 0.03}
            controls.update(kwargs)
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    paper_evaluate_baseline(matches, prices, **controls)

    def test_paper_evaluate_baseline_summarizes_daily_exposure_and_drawdown(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = [
            CsMarketPriceFixture(
                contest_hltv_id="2370001",
                map_index=1,
                team_hltv_id="9565",
                best_bid=0.30,
                best_ask=0.32,
                taken_at=datetime(2026, 1, 5, 17, 30, tzinfo=timezone.utc),
            ),
            CsMarketPriceFixture(
                contest_hltv_id="2370001",
                map_index=2,
                team_hltv_id="9565",
                best_bid=0.30,
                best_ask=0.32,
                taken_at=datetime(2026, 1, 6, 17, 30, tzinfo=timezone.utc),
            ),
        ]

        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03)

        self.assertEqual(summary.recommendations, 2)
        self.assertEqual(summary.daily_exposure["2026-01-05"]["recommendations"], 1)
        self.assertEqual(summary.daily_exposure["2026-01-05"]["pnl_per_unit_stake"], -1.0)
        self.assertAlmostEqual(summary.max_drawdown_per_unit_stake, 1.0)

    def test_write_paper_evaluation_artifact(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))
        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_paper_evaluation_artifact(summary, Path(tmp))

            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["candidates"], 4)
            self.assertTrue(path.name.startswith("cs-paper-evaluation-"))

    def test_write_accepted_paper_recommendations_artifact(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))
        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_accepted_paper_recommendations_artifact(summary, Path(tmp), max_items=1)

            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(len(payload["recommendations"]), 1)
            self.assertTrue(path.name.startswith("cs-accepted-paper-recommendations-"))

    def test_write_paper_recommendations_csv(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))
        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_paper_recommendations_csv(summary, Path(tmp))

            text = path.read_text(encoding="utf-8")

            self.assertIn("contest_hltv_id,map_index,team_id", text)
            self.assertIn("best_of,team_maps_played_90d", text)
            self.assertIn("sample_confidence,shrink_multiplier", text)
            self.assertTrue(path.name.startswith("cs-paper-recommendations-"))

    def test_write_accepted_paper_recommendations_csv(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))
        prices = load_market_price_fixtures(Path("tests/fixtures/cs_market_prices.json"))
        summary = paper_evaluate_baseline(matches, prices, min_edge=0.03)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_accepted_paper_recommendations_csv(summary, Path(tmp), max_items=1)

            lines = path.read_text(encoding="utf-8").splitlines()

            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[0].startswith("review_rank,contest_hltv_id"))
            self.assertTrue(lines[1].startswith("1,2370001,2"))
            self.assertTrue(all("edge_pass" in line for line in lines[1:]))
            self.assertTrue(path.name.startswith("cs-accepted-paper-recommendations-"))


if __name__ == "__main__":
    unittest.main()
