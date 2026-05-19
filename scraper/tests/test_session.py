from __future__ import annotations

import unittest

from scraper.session import playwright_proxy_config
from scraper.fetcher import _env_verify_tls


class SessionTests(unittest.TestCase):
    def test_playwright_proxy_config_splits_credentials(self) -> None:
        proxy = playwright_proxy_config("http://user%40x:pass%3Aword@gate.decodo.com:7000")

        self.assertEqual(
            proxy,
            {
                "server": "http://gate.decodo.com:7000",
                "username": "user@x",
                "password": "pass:word",
            },
        )

    def test_playwright_proxy_config_accepts_plain_server(self) -> None:
        self.assertEqual(playwright_proxy_config("http://gate.decodo.com:7000"), {"server": "http://gate.decodo.com:7000"})
        self.assertIsNone(playwright_proxy_config(""))

    def test_env_verify_tls_flag(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"HLTV_VERIFY_TLS": "false"}):
            self.assertFalse(_env_verify_tls())
        with patch.dict(os.environ, {"HLTV_VERIFY_TLS": "true"}):
            self.assertTrue(_env_verify_tls())


if __name__ == "__main__":
    unittest.main()
