from __future__ import annotations

import unittest
from datetime import date

from core.backtesting import build_walk_forward_windows


class WalkForwardTests(unittest.TestCase):
    def test_builds_non_overlapping_validation_windows(self) -> None:
        windows = build_walk_forward_windows(
            start=date(2025, 1, 1),
            end=date(2025, 4, 30),
            train_days=30,
            validate_days=14,
            step_days=14,
        )

        self.assertGreater(len(windows), 1)
        self.assertEqual(windows[0].validate_start, date(2025, 2, 1))
        self.assertLess(windows[0].validate_end, windows[1].validate_start)


if __name__ == "__main__":
    unittest.main()

