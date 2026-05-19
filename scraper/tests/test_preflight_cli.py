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

                backup_buffer = io.StringIO()
                with redirect_stdout(backup_buffer):
                    backup_code = main(["backup", "--out-dir", str(root / "backups")])

            status_payload = json.loads(status_buffer.getvalue())
            export_payload = json.loads(export_buffer.getvalue())
            preflight_payload = json.loads(preflight_buffer.getvalue())
            backup_payload = json.loads(backup_buffer.getvalue())
            backup_exists = Path(backup_payload["backup"]).exists()

        self.assertEqual(status_code, 0)
        self.assertEqual(export_code, 0)
        self.assertEqual(preflight_code, 1)
        self.assertEqual(backup_code, 0)
        self.assertEqual(status_payload["queue"]["total"], 0)
        self.assertEqual(export_payload["exported"], 1)
        self.assertFalse(preflight_payload["ok"])
        self.assertTrue(backup_exists)


if __name__ == "__main__":
    unittest.main()
