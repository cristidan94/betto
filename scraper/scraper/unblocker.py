from __future__ import annotations

import time
from urllib.parse import quote

from scraper.anti_detect import is_cloudflare_challenge
from scraper.config import ScraperConfig


# Decodo Site Unblocker renders JS + solves Cloudflare. It is flaky on heavy
# pages (a ~50s gateway timeout on roughly half of attempts), so callers retry.
DEFAULT_TIMEOUT = 150
DEFAULT_RETRIES = 4


def unblocker_configured(config: ScraperConfig) -> bool:
    return bool(config.unblocker_proxy and config.unblocker_user and config.unblocker_pass)


def fetch_via_unblocker(
    url: str,
    config: ScraperConfig,
    retries: int = DEFAULT_RETRIES,
    timeout: int = DEFAULT_TIMEOUT,
    sleep_between: float = 2.0,
) -> tuple[bool, str | None]:
    """Fetch a URL through the Decodo Site Unblocker with headless rendering.

    Returns (ok, html). ok is False if every attempt failed (timeout, gateway
    error 6xx, or a still-challenged page)."""
    if not unblocker_configured(config):
        return False, None
    proxies = {"http": _proxy_url(config), "https": _proxy_url(config)}
    headers = {"X-SU-Headless": "html"}
    last_html: str | None = None
    for attempt in range(retries):
        status, html = _request(url, proxies, headers, timeout)
        if _is_usable(status, html):
            return True, html
        last_html = html
        if attempt < retries - 1:
            time.sleep(sleep_between)
    return False, last_html


def _request(url: str, proxies: dict[str, str], headers: dict[str, str], timeout: int) -> tuple[int, str | None]:
    try:
        from curl_cffi import requests as curl_requests

        resp = curl_requests.get(url, proxies=proxies, headers=headers, timeout=timeout, verify=False)
        return int(resp.status_code), resp.text
    except Exception:
        return 0, None


def _is_usable(status: int, html: str | None) -> bool:
    if status != 200 or not html:
        return False
    stripped = html.lstrip()
    # The unblocker reports failures as a small JSON body (e.g. status_code 613).
    if stripped.startswith("{") and '"status":"failed"' in stripped[:200]:
        return False
    if len(html) < 5000:
        return False
    return not is_cloudflare_challenge(status, html)


def _proxy_url(config: ScraperConfig) -> str:
    scheme, _, host = config.unblocker_proxy.partition("://")
    if not host:
        scheme, host = "https", config.unblocker_proxy
    user = quote(config.unblocker_user, safe="")
    password = quote(config.unblocker_pass, safe="")
    return f"{scheme}://{user}:{password}@{host}"
