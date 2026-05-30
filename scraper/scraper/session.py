from __future__ import annotations

import logging
from typing import Any
from urllib.parse import unquote, urlsplit

_logger = logging.getLogger(__name__)


class PlaywrightSession:
    def __init__(self, proxy_url: str | None = None, verify_tls: bool = True) -> None:
        self.proxy_url = proxy_url
        self.verify_tls = verify_tls
        self._playwright = None
        self._browser = None
        self._context = None
        self._request_count = 0
        self._max_requests = 15

    def fetch(self, url: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
        if self._browser is None or self._request_count >= self._max_requests:
            self.close()
            self._start()
        if self._context is None:
            clean = {k: v for k, v in (headers or {}).items() if k.lower() != "user-agent"}
            self._context = self._browser.new_context(
                extra_http_headers=clean,
                ignore_https_errors=not self.verify_tls,
            )
        page = self._context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            status = response.status if response is not None else 0
            if status in {403, 503} or _is_challenge_page(page):
                page.wait_for_timeout(8000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                status = _final_status(page, status)
            else:
                page.wait_for_timeout(1500)
            html = page.content()
            self._request_count += 1
            return status, html
        finally:
            page.close()

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._request_count = 0

    def _start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        proxy = playwright_proxy_config(self.proxy_url)
        self._browser = self._playwright.chromium.launch(headless=True, proxy=proxy)


def _is_challenge_page(page: Any) -> bool:
    try:
        content = page.content().lower()
        return any(m in content for m in ("cf-challenge", "checking your browser", "just a moment"))
    except Exception:
        return False


def _final_status(page: Any, original_status: int) -> int:
    try:
        content = page.content().lower()
        if "hltv.org" in content and "cf-challenge" not in content and "checking your browser" not in content:
            return 200
    except Exception:
        pass
    return original_status


def playwright_proxy_config(proxy_url: str | None) -> dict[str, str] | None:
    if not proxy_url:
        return None
    parts = urlsplit(proxy_url)
    if not parts.scheme or not parts.netloc:
        return {"server": proxy_url}

    host = parts.hostname or ""
    server = f"{parts.scheme}://{host}"
    if parts.port is not None:
        server = f"{server}:{parts.port}"
    proxy = {"server": server}
    if parts.username:
        proxy["username"] = unquote(parts.username)
    if parts.password:
        proxy["password"] = unquote(parts.password)
    return proxy
