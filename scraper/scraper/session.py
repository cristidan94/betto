from __future__ import annotations

import logging
from urllib.parse import unquote, urlsplit

_logger = logging.getLogger(__name__)


class PlaywrightSession:
    def __init__(self, proxy_url: str | None = None, verify_tls: bool = True) -> None:
        self.proxy_url = proxy_url
        self.verify_tls = verify_tls
        self._playwright = None
        self._browser = None
        self._request_count = 0
        self._max_requests = 15

    def fetch(self, url: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
        if self._browser is None or self._request_count >= self._max_requests:
            self.close()
            self._start()
        context = self._browser.new_context(extra_http_headers=headers or {}, ignore_https_errors=not self.verify_tls)
        page = context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            status = response.status if response is not None else 0
            html = page.content()
            self._request_count += 1
            return status, html
        finally:
            context.close()

    def close(self) -> None:
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
