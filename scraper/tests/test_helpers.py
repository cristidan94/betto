from __future__ import annotations

import unittest

from scraper.anti_detect import extract_url_pattern, is_cloudflare_challenge, is_usable_hltv_html
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter


class HelperTests(unittest.TestCase):
    def test_cloudflare_detection_and_patterns(self) -> None:
        self.assertTrue(is_cloudflare_challenge(403, "<html>Access denied</html>"))
        self.assertTrue(is_cloudflare_challenge(200, '<div id="cf-challenge-running"></div>'))
        self.assertFalse(is_cloudflare_challenge(200, "<html>Normal</html>"))
        self.assertTrue(is_usable_hltv_html(400, '<html><a href="https://www.hltv.org/results">HLTV</a></html>'))
        self.assertFalse(is_usable_hltv_html(400, "<html>Bad Request</html>"))
        self.assertEqual(extract_url_pattern("https://www.hltv.org/stats/matches/mapstatsid/789/slug"), "/stats/matches/mapstatsid/")
        self.assertEqual(extract_url_pattern("https://www.hltv.org/results?offset=100"), "/results")

    def test_proxy_rotator_and_rate_limiter(self) -> None:
        rotator = ProxyRotator("http://user-session-{session}:pass@gate.proxy.com:10000", ["us"])
        rotator.start_sticky_session()
        proxy = rotator.next_proxy()
        rotator.end_sticky_session()

        limiter = RateLimiter(min_delay=1, max_delay=2, daily_cap=1)
        limiter.next_delay()

        self.assertIsNotNone(proxy)
        assert proxy is not None
        self.assertIn("session-", proxy)
        self.assertTrue(limiter.daily_cap_reached())


if __name__ == "__main__":
    unittest.main()
