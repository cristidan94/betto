from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from core.cli.main import main


def scheduled_fixture() -> dict[str, object]:
    return {
        "hltv_id": "scheduled",
        "scheduled_at": "2026-05-01T00:00:00Z",
        "best_of": 1,
        "status": "scheduled",
        "team_a": {"hltv_id": "1", "name": "NAVI"},
        "team_b": {"hltv_id": "2", "name": "Vitality"},
        "event": {"hltv_id": "100", "name": "Fixture Cup"},
        "players": [],
        "maps": [],
    }


class CliTests(unittest.TestCase):
    def test_paper_evaluate_returns_structured_error_for_invalid_controls(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            code = main(
                [
                    "paper-evaluate-cs-baseline",
                    "--corpus",
                    "tests/fixtures/cs_match_001.json",
                    "--markets",
                    "tests/fixtures/cs_market_prices.json",
                    "--market-bankroll-cap",
                    "0",
                ]
        )

        output = stdout.getvalue()
        payload = json.loads(output[output.rfind("\n{") + 1 :])

        self.assertEqual(code, 1)
        self.assertEqual(payload["error"], "paper_evaluation_invalid_controls")
        self.assertIn("market_bankroll_cap", payload["detail"])

    def test_strategy_report_returns_structured_error_for_invalid_controls(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            code = main(
                [
                    "report-cs-baseline-strategy",
                    "--corpus",
                    "tests/fixtures/cs_match_001.json",
                    "--markets",
                    "tests/fixtures/cs_market_prices.json",
                    "--market-bankroll-cap",
                    "0",
                ]
            )

        output = stdout.getvalue()
        payload = json.loads(output[output.rfind("\n{") + 1 :])

        self.assertEqual(code, 1)
        self.assertEqual(payload["error"], "strategy_report_invalid_controls")
        self.assertIn("market_bankroll_cap", payload["detail"])

    def test_evaluate_baseline_returns_structured_error_for_empty_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "scheduled.json"
            fixture.write_text(json.dumps(scheduled_fixture()), encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["evaluate-cs-baseline", "--fixtures", str(fixture)])

        output = stdout.getvalue()
        payload = json.loads(output[output.rfind("\n{") + 1 :])

        self.assertEqual(code, 1)
        self.assertEqual(payload["error"], "baseline_evaluation_failed")
        self.assertIn("no training rows", payload["detail"])

    def test_convert_hltv_scraped_imports_fixture_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "scraped"
            out_dir = Path(tmp) / "fixtures"
            raw_dir.mkdir()
            (raw_dir / "2371234.json").write_text(json.dumps({"hltv_id": "2371234"}), encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["convert-hltv-scraped", "--raw-dir", str(raw_dir), "--out-dir", str(out_dir)])

            output = stdout.getvalue()
            payload = json.loads(output[output.rfind("\n{") + 1 :])
            imported_path_exists = (out_dir / "2371234.json").exists()

        self.assertEqual(code, 0)
        self.assertEqual(payload["imported"], 1)
        self.assertTrue(imported_path_exists)


if __name__ == "__main__":
    unittest.main()
