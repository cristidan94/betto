from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from sports.cs.fixtures import load_fixture_corpus
from sports.cs.models import evaluate_baseline_walk_forward, summarize_walk_forward_results, walk_forward_payload


class CsWalkForwardTests(unittest.TestCase):
    def test_evaluate_baseline_walk_forward(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/corpus"))

        results = evaluate_baseline_walk_forward(
            matches,
            start=date(2026, 1, 1),
            end=date(2026, 3, 31),
            train_days=30,
            validate_days=20,
            step_days=15,
        )

        self.assertGreaterEqual(len(results), 2)
        self.assertTrue(all(result.rows > 0 for result in results))
        self.assertIn("brier_score", results[0].metrics)

    def test_walk_forward_payload_serializes_dates(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/corpus"))
        results = evaluate_baseline_walk_forward(
            matches,
            start=date(2026, 1, 1),
            end=date(2026, 3, 31),
            train_days=30,
            validate_days=20,
            step_days=15,
        )

        payload = walk_forward_payload(results)

        self.assertIsInstance(payload[0]["window"]["train_start"], str)  # type: ignore[index]

    def test_summarize_walk_forward_results_weights_by_rows(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/corpus"))
        results = evaluate_baseline_walk_forward(
            matches,
            start=date(2026, 1, 1),
            end=date(2026, 3, 31),
            train_days=30,
            validate_days=20,
            step_days=15,
        )

        summary = summarize_walk_forward_results(results)

        self.assertEqual(summary["windows"], len(results))
        self.assertEqual(summary["rows"], sum(result.rows for result in results))
        self.assertIsInstance(summary["brier_score"], float)


if __name__ == "__main__":
    unittest.main()
