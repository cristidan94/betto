from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from scraper.anti_detect import extract_url_pattern, is_usable_hltv_html, random_headers
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.session import PlaywrightSession
from scraper.tracking_db import TrackingDB


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

    def fetch(self, url: str) -> FetchResult:
        if self._limiter.daily_cap_reached():
            return FetchResult(0, "daily cap reached", "rate_limiter", 0, 17)
        if self._db.needs_playwright(extract_url_pattern(url)):
            result = self._fetch_playwright(url)
            if result.ok:
                self._limiter.record_success()
            else:
                self._limiter.record_failure()
            return result
        result = self._fetch_curl(url)
        if result.ok:
            self._limiter.record_success()
            return result
        self._db.record_block(extract_url_pattern(url))
        self._limiter.record_failure()
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
        try:
            from curl_cffi import requests as curl_requests

            proxies = {"http": proxy, "https": proxy} if proxy else None
            resp = curl_requests.get(
                url,
                headers=random_headers(),
                proxies=proxies,
                timeout=45,
                impersonate="chrome124",
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
