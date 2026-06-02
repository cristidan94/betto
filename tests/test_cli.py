from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from core.cli.main import main
from core.config.settings import Settings


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
            (raw_dir / "manifest.json").write_text(json.dumps({"files": ["2371234.json"]}), encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["convert-hltv-scraped", "--raw-dir", str(raw_dir), "--out-dir", str(out_dir)])

            output = stdout.getvalue()
            payload = json.loads(output[output.rfind("\n{") + 1 :])
            imported_path_exists = (out_dir / "2371234.json").exists()
            manifest_path_exists = (out_dir / "manifest.json").exists()

        self.assertEqual(code, 0)
        self.assertEqual(payload["imported"], 1)
        self.assertTrue(imported_path_exists)
        self.assertFalse(manifest_path_exists)

    def test_db_ingest_hltv_scraped_help_is_registered(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            main(["db-ingest-hltv-scraped", "--help"])

        self.assertEqual(raised.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn("--scraped-dir", output)
        self.assertIn("--force", output)

    def test_db_ingest_hltv_scraped_records_raw_object_after_successful_domain_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scraped_dir = root / "scraped"
            scraped_dir.mkdir()
            sample = Path("tests/fixtures/hltv_scraped_sample.json")
            (scraped_dir / "2349691.json").write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
            (scraped_dir / "manifest.json").write_text(json.dumps({"files": ["2349691.json"]}), encoding="utf-8")
            db = FakeCliDb()
            stdout = io.StringIO()

            with _patched_cli_db(root, db), redirect_stdout(stdout):
                code = main(["db-ingest-hltv-scraped", "--scraped-dir", str(scraped_dir)])

            payload = json.loads(stdout.getvalue()[stdout.getvalue().rfind("\n{") + 1 :])
            sql_calls = [sql for sql, _ in db.calls]
            raw_index = next(index for index, sql in enumerate(sql_calls) if "INSERT INTO raw_objects" in sql)
            stats_index = next(index for index, sql in enumerate(sql_calls) if "INSERT INTO cs_player_map_stats" in sql)

        self.assertEqual(code, 0)
        self.assertEqual(payload["fixtures_found"], 1)
        self.assertEqual(payload["ingested"], 1)
        self.assertEqual(payload["failed"], 0)
        self.assertEqual(payload["participants_upserted"], 12)
        self.assertEqual(payload["lineups_upserted"], 10)
        self.assertEqual(payload["player_stats_upserted"], 10)
        self.assertGreater(raw_index, stats_index)
        self.assertTrue(any(sql.startswith("SAVEPOINT") for sql in sql_calls))
        self.assertTrue(any(sql.startswith("RELEASE SAVEPOINT") for sql in sql_calls))

    def test_db_ingest_hltv_scraped_rolls_back_failed_fixture_and_does_not_count_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scraped_dir = root / "scraped"
            scraped_dir.mkdir()
            sample = Path("tests/fixtures/hltv_scraped_sample.json")
            (scraped_dir / "2349691.json").write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
            db = FakeCliDb(fail_on="INSERT INTO cs_map_results")
            stdout = io.StringIO()

            with _patched_cli_db(root, db), redirect_stdout(stdout):
                code = main(["db-ingest-hltv-scraped", "--scraped-dir", str(scraped_dir)])

            payload = json.loads(stdout.getvalue()[stdout.getvalue().rfind("\n{") + 1 :])
            sql_calls = [sql for sql, _ in db.calls]

        self.assertEqual(code, 0)
        self.assertEqual(payload["ingested"], 0)
        self.assertEqual(payload["failed"], 1)
        self.assertEqual(payload["participants_upserted"], 0)
        self.assertFalse(any("INSERT INTO raw_objects" in sql for sql in sql_calls))
        self.assertTrue(any(sql.startswith("ROLLBACK TO SAVEPOINT") for sql in sql_calls))


class FakeCliDb:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> object:
        self.calls.append((sql, params))
        if self.fail_on is not None and self.fail_on in sql:
            raise RuntimeError("forced failure")
        if "SELECT source_id FROM raw_objects" in sql:
            return []
        return []


class FakeCliPostgresExecutor:
    def __init__(self, db: FakeCliDb) -> None:
        self.db = db

    def __enter__(self) -> FakeCliDb:
        return self.db

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


def _patched_cli_db(root: Path, db: FakeCliDb):
    settings = Settings(
        env="test",
        project_root=root,
        data_dir=root / ".betto",
        raw_store_dir=root / ".betto" / "raw",
        database_url="postgresql://test",
        redis_url="redis://test",
        polymarket_gamma_url="https://example.com/gamma",
        polymarket_clob_url="https://example.com/clob",
        polymarket_snapshot_interval_sec=300,
        default_timezone="UTC",
        oddspapi_api_key="",
        oddspapi_base_url="https://example.com/odds",
    )
    return patch.multiple(
        "core.cli.main",
        load_settings=lambda: settings,
        PostgresExecutor=lambda database_url: FakeCliPostgresExecutor(db),
    )


if __name__ == "__main__":
    unittest.main()
