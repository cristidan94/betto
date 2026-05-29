from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scraper.cli import main
from scraper.config import ScraperConfig
from scraper.preflight import collect_preflight
from scraper.tracking_db import TrackingDB


class PreflightCliTests(unittest.TestCase):
    def test_collect_preflight_reports_ready_when_requirements_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = ScraperConfig(
                proxy_url="http://user:pass@proxy.example:10000",
                raw_dir=root / "raw",
                output_dir=root / "out",
                db_path=root / "db" / "hltv.db",
            )

            result = collect_preflight(config, import_checker=lambda name: True, browser_checker=lambda: True, create_dirs=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["checks"]["dependencies"]["curl_cffi"]["ok"])
        self.assertTrue(result["checks"]["paths"]["raw_dir"]["exists"])

    def test_collect_preflight_flags_placeholder_proxy_and_missing_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = ScraperConfig(
                proxy_url="http://user:password@proxy.example:10000",
                raw_dir=root / "raw",
                output_dir=root / "out",
                db_path=root / "db" / "hltv.db",
            )

            result = collect_preflight(
                config,
                import_checker=lambda name: name != "playwright",
                browser_checker=lambda: True,
                create_dirs=True,
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["proxy"]["ok"])
        self.assertFalse(result["checks"]["browser"]["ok"])
        self.assertFalse(result["checks"]["dependencies"]["playwright"]["ok"])

    def test_cli_status_export_and_preflight_are_no_network_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_dir = root / "out"
            out_dir.mkdir()
            (out_dir / "2371234.json").write_text('{"hltv_id": "2371234"}', encoding="utf-8")
            env = {
                "HLTV_RAW_DIR": str(root / "raw"),
                "HLTV_OUTPUT_DIR": str(out_dir),
                "HLTV_DB_PATH": str(root / "db" / "hltv.db"),
                "HLTV_PROXY_URL": "http://user:password@proxy.example:10000",
            }
            with patch.dict(os.environ, env, clear=True), patch("scraper.preflight._playwright_browser_available", return_value=True):
                status_buffer = io.StringIO()
                with redirect_stdout(status_buffer):
                    status_code = main(["status"])

                export_buffer = io.StringIO()
                with redirect_stdout(export_buffer):
                    export_code = main(["export", "--out-dir", str(root / "fixtures")])

                preflight_buffer = io.StringIO()
                with redirect_stdout(preflight_buffer):
                    preflight_code = main(["preflight", "--create-dirs"])

                verbose_status_buffer = io.StringIO()
                with redirect_stdout(verbose_status_buffer):
                    verbose_status_code = main(["status", "--verbose", "--recent", "2"])

                backup_buffer = io.StringIO()
                with redirect_stdout(backup_buffer):
                    backup_code = main(["backup", "--out-dir", str(root / "backups")])

                manifest_buffer = io.StringIO()
                with redirect_stdout(manifest_buffer):
                    manifest_code = main(["manifest", "--out", str(root / "out" / "manifest.json"), "--include-files"])

                report_buffer = io.StringIO()
                with redirect_stdout(report_buffer):
                    report_code = main(["report", "--out", str(root / "out" / "report.html")])

                quality_buffer = io.StringIO()
                with redirect_stdout(quality_buffer):
                    quality_code = main(["quality-report", "--sample", "2"])

                validate_buffer = io.StringIO()
                with redirect_stdout(validate_buffer):
                    validate_code = main(["validate-fixtures", "--sample", "2"])

                health_buffer = io.StringIO()
                with redirect_stdout(health_buffer):
                    health_code = main(["health"])

                with patch("scraper.cli.send_webhook", return_value={"sent": False, "reason": "not_configured"}) as webhook:
                    alert_buffer = io.StringIO()
                    with redirect_stdout(alert_buffer):
                        alert_code = main(["alert", "--title", "Test status", "--recent", "2", "--sample", "2"])

            status_payload = json.loads(status_buffer.getvalue())
            export_payload = json.loads(export_buffer.getvalue())
            preflight_payload = json.loads(preflight_buffer.getvalue())
            verbose_status_payload = json.loads(verbose_status_buffer.getvalue())
            backup_payload = json.loads(backup_buffer.getvalue())
            manifest_payload = json.loads(manifest_buffer.getvalue())
            manifest_json = json.loads(Path(manifest_payload["manifest"]).read_text(encoding="utf-8"))
            report_payload = json.loads(report_buffer.getvalue())
            report_html = Path(report_payload["report"]).read_text(encoding="utf-8")
            quality_payload = json.loads(quality_buffer.getvalue())
            validate_payload = json.loads(validate_buffer.getvalue())
            health_payload = json.loads(health_buffer.getvalue())
            alert_payload = json.loads(alert_buffer.getvalue())
            backup_exists = Path(backup_payload["backup"]).exists()

        self.assertEqual(status_code, 0)
        self.assertEqual(export_code, 0)
        self.assertEqual(preflight_code, 1)
        self.assertEqual(verbose_status_code, 0)
        self.assertEqual(backup_code, 0)
        self.assertEqual(manifest_code, 0)
        self.assertEqual(report_code, 0)
        self.assertEqual(quality_code, 0)
        self.assertEqual(validate_code, 1)
        self.assertEqual(health_code, 1)
        self.assertEqual(alert_code, 0)
        self.assertEqual(status_payload["queue"]["total"], 0)
        self.assertIn("backfill", verbose_status_payload)
        self.assertIn("files", verbose_status_payload)
        self.assertEqual(manifest_json["schema_version"], "hltv-fixture-v1")
        self.assertEqual(manifest_json["file_count"], 1)
        self.assertEqual(len(manifest_json["files"]), 1)
        self.assertIn("HLTV Scraper Report", report_html)
        self.assertEqual(quality_payload["coverage"]["json_files"], 1)
        self.assertFalse(validate_payload["ok"])
        self.assertFalse(health_payload["ok"])
        self.assertEqual(alert_payload["reason"], "not_configured")
        self.assertEqual(webhook.call_args.args[1], "Test status")
        self.assertEqual(export_payload["exported"], 1)
        self.assertFalse(preflight_payload["ok"])
        self.assertTrue(backup_exists)

    def test_admin_cli_failed_retry_and_reset_backfill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            out.mkdir()
            (out / "2371234.json").write_text(
                json.dumps(
                    {
                        "schema_version": "hltv-fixture-v1",
                        "hltv_id": "2371234",
                        "scheduled_at": "2026-01-01T00:00:00+00:00",
                        "best_of": 1,
                        "status": "finished",
                        "team_a": {"hltv_id": "1", "name": "A"},
                        "team_b": {"hltv_id": "2", "name": "B"},
                        "event": {"hltv_id": "10", "name": "IEM Cologne", "tier": 1},
                        "players": [],
                        "maps": [{"map_index": 1, "map_name": "Inferno", "team_a_score": 13, "team_b_score": 9, "winner_hltv_id": "1", "player_stats": {}}],
                        "vetoes": [],
                        "source": {"stats_url": "https://www.hltv.org/stats/matches/1/a-vs-b"},
                    }
                ),
                encoding="utf-8",
            )
            env = {
                "HLTV_RAW_DIR": str(root / "raw"),
                "HLTV_OUTPUT_DIR": str(out),
                "HLTV_DB_PATH": str(root / "db" / "hltv.db"),
            }
            db = TrackingDB(root / "db" / "hltv.db")
            db.upsert_match("2371234", "/matches/2371234/a-vs-b")
            db.record_error("2371234", "HTTP 403")
            db.close()

            with patch.dict(os.environ, env, clear=True):
                failed_buffer = io.StringIO()
                with redirect_stdout(failed_buffer):
                    failed_code = main(["failed", "--limit", "5"])

                retry_buffer = io.StringIO()
                with redirect_stdout(retry_buffer):
                    retry_code = main(["retry-failed", "--limit", "5"])

                reset_buffer = io.StringIO()
                with redirect_stdout(reset_buffer):
                    reset_code = main(["reset-backfill", "--start-page", "12"])

                show_buffer = io.StringIO()
                with redirect_stdout(show_buffer):
                    show_code = main(["show-match", "2371234"])

                gaps_buffer = io.StringIO()
                with redirect_stdout(gaps_buffer):
                    gaps_code = main(["stats-gaps"])

                retry_stats_buffer = io.StringIO()
                with redirect_stdout(retry_stats_buffer):
                    retry_stats_code = main(["retry-stats-only"])

        failed_payload = json.loads(failed_buffer.getvalue())
        retry_payload = json.loads(retry_buffer.getvalue())
        reset_payload = json.loads(reset_buffer.getvalue())
        show_payload = json.loads(show_buffer.getvalue())
        gaps_payload = json.loads(gaps_buffer.getvalue())
        retry_stats_payload = json.loads(retry_stats_buffer.getvalue())

        self.assertEqual(failed_code, 0)
        self.assertEqual(retry_code, 0)
        self.assertEqual(reset_code, 0)
        self.assertEqual(show_code, 0)
        self.assertEqual(gaps_code, 0)
        self.assertEqual(retry_stats_code, 0)
        self.assertEqual(failed_payload["matches"][0]["match_id"], "2371234")
        self.assertEqual(retry_payload["queued_for_retry"], 1)
        self.assertEqual(reset_payload["next_offset"], 1200)
        self.assertEqual(show_payload["match_id"], "2371234")
        self.assertEqual(show_payload["queue"]["match_id"], "2371234")
        self.assertEqual(gaps_payload["matches"][0]["match_id"], "2371234")
        self.assertEqual(retry_stats_payload["queued_for_retry"], 1)

    def test_reparse_raw_regenerates_fixture_without_network(self) -> None:
        match_html = """
        <html><body>
          <div data-unix="1772539200000"></div>
          <a href="/team/4608/navi">NAVI</a>
          <a href="/team/6667/faze">FaZe</a>
          <a href="/events/7148/iem-katowice">IEM Katowice</a>
          <div>Inferno 13 - 9 <a href="/stats/matches/mapstatsid/98765/slug">map stats</a></div>
        </body></html>
        """
        map_html = """
        <table>
          <tr><td><a href="/player/7998/s1mple">s1mple</a></td><td>25 - 18</td><td>5</td><td>88.5</td><td>76.2%</td><td>1.32</td></tr>
        </table>
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_match = root / "raw" / "matches" / "2371234"
            raw_match.mkdir(parents=True)
            (raw_match / "match.html").write_text(match_html, encoding="utf-8")
            (raw_match / "map_98765.html").write_text(map_html, encoding="utf-8")
            env = {
                "HLTV_RAW_DIR": str(root / "raw"),
                "HLTV_OUTPUT_DIR": str(root / "out"),
                "HLTV_DB_PATH": str(root / "db" / "hltv.db"),
            }
            with patch.dict(os.environ, env, clear=True):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = main(["reparse-raw"])
            payload = json.loads((root / "out" / "2371234.json").read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buffer.getvalue())["reparsed"], 1)
        self.assertEqual(payload["event"]["tier"], 1)
        self.assertEqual(payload["maps"][0]["player_stats"]["s1mple"]["rating"], 1.32)


if __name__ == "__main__":
    unittest.main()
