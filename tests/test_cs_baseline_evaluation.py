from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sports.cs.models import calibration_payload_from_fixtures, evaluate_baseline_from_fixtures


class CsBaselineEvaluationTests(unittest.TestCase):
    def test_evaluate_baseline_from_fixture_writes_artifact(self) -> None:
        fixture = Path("tests/fixtures/cs_match_001.json").resolve()
        with tempfile.TemporaryDirectory() as tmp:
            result = evaluate_baseline_from_fixtures([fixture], Path(tmp))

            self.assertEqual(result.rows, 4)
            self.assertIn("brier_score", result.metrics)
            self.assertIsNotNone(result.artifact_path)
            assert result.artifact_path is not None
            self.assertTrue(result.artifact_path.exists())

    def test_calibration_payload_from_fixtures(self) -> None:
        fixture = Path("tests/fixtures/cs_match_001.json").resolve()

        payload = calibration_payload_from_fixtures([fixture])

        self.assertEqual(len(payload), 10)


if __name__ == "__main__":
    unittest.main()

