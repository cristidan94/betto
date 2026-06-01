from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from scraper.anti_detect import extract_url_pattern, is_usable_hltv_html, random_headers
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.session import PlaywrightSession
from scraper.tracking_db import TrackingDB


# curl_cffi browser fingerprints that reliably pass HLTV's Cloudflare edge.
# Safari impersonations are excluded: they consistently draw the managed
# challenge. Each retry rotates the fingerprint (and the proxy IP/region) so an
# intermittent block on one combination is retried on a fresh one.
CURL_IMPERSONATIONS = ("chrome124", "chrome120", "chrome131", "chrome116")
DEFAULT_CURL_ATTEMPTS = 3


@dataclass(frozen=True)
class FetchResult:
    status: int
    html: str
    fetcher_type: str
    elapsed_ms: int
    content_bytes: int

    @property
    def ok(self) -> bool:
        return is_usable_hltv_html(self.status, self.html)


class HltvFetcher:
    def __init__(self, proxy: ProxyRotator, rate_limiter: RateLimiter, db: TrackingDB, raw_dir: Path) -> None:
        self._proxy = proxy
        self._limiter = rate_limiter
        self._db = db
        self._raw_dir = raw_dir
        self._playwright: PlaywrightSession | None = None
        self._verify_tls = _env_verify_tls()
        self._curl_attempts = _env_curl_attempts()
        self._use_playwright = _env_use_playwright()
        self._impersonate_index = 0

    def fetch(self, url: str) -> FetchResult:
        if self._limiter.daily_cap_reached():
            return FetchResult(0, "daily cap reached", "rate_limiter", 0, 17)
        # Always try curl_cffi first: it is the only path that clears HLTV's
        # Cloudflare edge, and it does so intermittently, so we retry with a
        # rotated fingerprint and a fresh proxy IP on each attempt. (Headless
        # Playwright cannot solve the managed challenge, so it is only a
        # last-resort fallback and can be disabled entirely via env.)
        result = self._fetch_curl(url)
        for attempt in range(1, self._curl_attempts):
            if result.ok:
                break
            self._limiter.record_failure()
            if result.status == 404:
                return result
            self._limiter.sleep()
            result = self._fetch_curl(url)
        if result.ok:
            self._limiter.record_success()
            return result
        self._db.record_block(extract_url_pattern(url))
        self._limiter.record_failure()
        if not self._use_playwright:
            return result
        self._limiter.sleep()
        fallback = self._fetch_playwright(url)
        if fallback.ok:
            self._limiter.record_success()
        else:
            self._limiter.record_failure()
        return fallback

    def close(self) -> None:
        if self._playwright is not None:
            self._playwright.close()
            self._playwright = None

    def _fetch_curl(self, url: str) -> FetchResult:
        start = time.perf_counter()
        proxy = self._proxy.next_proxy()
        impersonate = CURL_IMPERSONATIONS[self._impersonate_index % len(CURL_IMPERSONATIONS)]
        self._impersonate_index += 1
        try:
            from curl_cffi import requests as curl_requests

            proxies = {"http": proxy, "https": proxy} if proxy else None
            resp = curl_requests.get(
                url,
                headers=random_headers(),
                proxies=proxies,
                timeout=45,
                impersonate=impersonate,
                verify=self._verify_tls,
            )
            html = resp.text
            status = int(resp.status_code)
        except Exception as exc:
            html = str(exc)
            status = 0
        elapsed = int((time.perf_counter() - start) * 1000)
        result = FetchResult(status, html, "curl_cffi", elapsed, len(html.encode("utf-8", errors="ignore")))
        self._db.log_request(url, result.status, result.fetcher_type, self._proxy.current_region, result.content_bytes, result.elapsed_ms)
        self._limiter.record_request()
        return result

    def _fetch_playwright(self, url: str) -> FetchResult:
        start = time.perf_counter()
        proxy = self._proxy.next_proxy()
        if self._playwright is None:
            self._playwright = PlaywrightSession(proxy, verify_tls=self._verify_tls)
        else:
            self._playwright.proxy_url = proxy
        try:
            status, html = self._playwright.fetch(url, random_headers())
        except Exception as exc:
            status, html = 0, str(exc)
        elapsed = int((time.perf_counter() - start) * 1000)
        result = FetchResult(status, html, "playwright", elapsed, len(html.encode("utf-8", errors="ignore")))
        self._db.log_request(url, result.status, result.fetcher_type, self._proxy.current_region, result.content_bytes, result.elapsed_ms)
        self._limiter.record_request()
        return result

    def _save_raw(self, match_id: str, filename: str, html: str) -> Path:
        directory = self._raw_dir / "matches" / match_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        path.write_text(html, encoding="utf-8")
        return path


def _env_verify_tls() -> bool:
    import os

    value = os.environ.get("HLTV_VERIFY_TLS", "true")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_curl_attempts() -> int:
    import os

    try:
        attempts = int(os.environ.get("HLTV_CURL_ATTEMPTS", str(DEFAULT_CURL_ATTEMPTS)))
    except ValueError:
        return DEFAULT_CURL_ATTEMPTS
    return max(1, attempts)


def _env_use_playwright() -> bool:
    import os

    value = os.environ.get("HLTV_USE_PLAYWRIGHT", "true")
    return value.strip().lower() not in {"0", "false", "no", "off"}
