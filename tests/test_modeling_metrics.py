from __future__ import annotations

import unittest

from core.modeling import brier_score, calibration_buckets, expected_calibration_error, log_loss


class ModelingMetricsTests(unittest.TestCase):
    def test_brier_score(self) -> None:
        self.assertAlmostEqual(brier_score([0.75, 0.25], [1, 0]), 0.0625)

    def test_log_loss_rewards_confident_correct_predictions(self) -> None:
        self.assertLess(log_loss([0.9, 0.1], [1, 0]), log_loss([0.6, 0.4], [1, 0]))

    def test_calibration_buckets(self) -> None:
        buckets = calibration_buckets([0.15, 0.85], [0, 1], bucket_count=2)

        self.assertEqual(buckets[0].count, 1)
        self.assertEqual(buckets[1].count, 1)
        self.assertEqual(buckets[1].observed_rate, 1.0)

    def test_expected_calibration_error(self) -> None:
        ece = expected_calibration_error([0.2, 0.8], [0, 1], bucket_count=2)

        self.assertAlmostEqual(ece, 0.2)

    def test_metrics_validate_inputs(self) -> None:
        with self.assertRaises(ValueError):
            brier_score([], [])
        with self.assertRaises(ValueError):
            log_loss([1.2], [1])


if __name__ == "__main__":
    unittest.main()

