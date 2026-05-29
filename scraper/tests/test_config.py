from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scraper.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("scraper.config.load_dotenv", return_value=None):
            config = load_config()

        self.assertEqual(config.proxy_url, "")
        self.assertEqual(config.min_delay, 8)
        self.assertEqual(config.max_delay, 15)
        self.assertEqual(config.daily_cap, 5000)
        self.assertIn("us", config.proxy_regions)

    def test_load_config_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HLTV_PROXY_URL": "http://test:pass@proxy:8080",
                "HLTV_MIN_DELAY": "3",
                "HLTV_DAILY_CAP": "100",
                "HLTV_PROXY_REGIONS": "de,fr",
                "HLTV_VERIFY_TLS": "false",
                "HLTV_EVENT_ALLOW_LIST": "IEM,BLAST Premier,CCT",
                "HLTV_EVENT_TIER_OVERRIDES": "IEM Katowice=1,CCT=2",
                "HLTV_BACKFILL_MAX_PAGE": "300",
                "HLTV_BACKFILL_STOP_DATE": "2023-09-27",
                "HLTV_ALERT_WEBHOOK_URL": "https://example.invalid/hook",
            },
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.proxy_url, "http://test:pass@proxy:8080")
        self.assertEqual(config.min_delay, 3)
        self.assertEqual(config.daily_cap, 100)
        self.assertEqual(config.proxy_regions, ["de", "fr"])
        self.assertFalse(config.verify_tls)
        self.assertEqual(config.event_allow_list, ["IEM", "BLAST Premier", "CCT"])
        self.assertEqual(config.event_tier_overrides, {"IEM Katowice": 1, "CCT": 2})
        self.assertEqual(config.backfill_max_page, 300)
        self.assertEqual(config.backfill_stop_date, "2023-09-27")
        self.assertEqual(config.alert_webhook_url, "https://example.invalid/hook")

    def test_tier_registry_path_loads_overrides(self) -> None:
        import tempfile
        yaml_content = "events:\n  - pattern: TestEvent\n    tier: 3\nallow_list:\n  - TestEvent\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            f.flush()
            with patch.dict(os.environ, {"HLTV_TIER_REGISTRY_PATH": f.name}, clear=True), patch("scraper.config.load_dotenv", return_value=None):
                config = load_config()

        self.assertEqual(config.event_tier_overrides, {"TestEvent": 3})
        self.assertEqual(config.event_allow_list, ["TestEvent"])
        self.assertIsNotNone(config.tier_registry_path)

    def test_env_overrides_beat_registry(self) -> None:
        import tempfile
        yaml_content = "events:\n  - pattern: FromYaml\n    tier: 3\nallow_list:\n  - FromYaml\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            f.flush()
            with patch.dict(os.environ, {
                "HLTV_TIER_REGISTRY_PATH": f.name,
                "HLTV_EVENT_TIER_OVERRIDES": "FromEnv=1",
            }, clear=True), patch("scraper.config.load_dotenv", return_value=None):
                config = load_config()

        self.assertEqual(config.event_tier_overrides, {"FromEnv": 1})

    def test_event_allow_list_not_empty(self) -> None:
        config = load_config()

        self.assertGreater(len(config.event_allow_list), 10)
        self.assertTrue(any("IEM" in item for item in config.event_allow_list))
        self.assertTrue(any("Major" in item for item in config.event_allow_list))


if __name__ == "__main__":
    unittest.main()
