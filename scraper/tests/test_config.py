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
            },
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.proxy_url, "http://test:pass@proxy:8080")
        self.assertEqual(config.min_delay, 3)
        self.assertEqual(config.daily_cap, 100)
        self.assertEqual(config.proxy_regions, ["de", "fr"])
        self.assertFalse(config.verify_tls)

    def test_event_allow_list_not_empty(self) -> None:
        config = load_config()

        self.assertGreater(len(config.event_allow_list), 10)
        self.assertTrue(any("IEM" in item for item in config.event_allow_list))
        self.assertTrue(any("Major" in item for item in config.event_allow_list))


if __name__ == "__main__":
    unittest.main()
