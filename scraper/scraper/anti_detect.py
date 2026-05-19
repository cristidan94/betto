from __future__ import annotations

import random
from urllib.parse import urlparse


HEADER_SETS = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    },
]


def random_headers() -> dict[str, str]:
    return dict(random.choice(HEADER_SETS))


def is_cloudflare_challenge(status: int, html: str) -> bool:
    if status in {403, 429, 503}:
        return True
    lowered = html.lower()
    markers = ("cf-challenge", "checking your browser", "access denied", "rate limited")
    return any(marker in lowered for marker in markers)


def is_usable_hltv_html(status: int, html: str) -> bool:
    if is_cloudflare_challenge(status, html):
        return False
    if 200 <= status < 400:
        return True
    lowered = html.lower()
    return status == 400 and "<html" in lowered and "hltv.org" in lowered


def extract_url_pattern(url: str) -> str:
    path = urlparse(url).path
    if path.startswith("/stats/matches/mapstatsid/"):
        return "/stats/matches/mapstatsid/"
    if path.startswith("/stats/matches/"):
        return "/stats/matches/"
    if path.startswith("/matches/"):
        return "/matches/"
    if path.startswith("/results"):
        return "/results"
    return path or "/"
