from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from scraper.config import ScraperConfig
from scraper.fetcher import HltvFetcher
from scraper.rate_limiter import RateLimiter

log = logging.getLogger(__name__)


def scrape_rankings(
    fetcher: HltvFetcher,
    limiter: RateLimiter,
    config: ScraperConfig,
    ranking_date: date | None = None,
) -> dict[str, Any]:
    if ranking_date is None:
        ranking_date = _latest_monday()
    url = f"https://www.hltv.org/ranking/teams/{ranking_date.year}/{ranking_date.strftime('%B').lower()}/{ranking_date.day}"
    out_dir = config.raw_dir / "rankings"
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = ranking_date.isoformat()
    json_path = out_dir / f"{date_str}.json"
    if json_path.exists():
        return {"status": "skipped", "date": date_str, "path": str(json_path)}
    limiter.sleep()
    result = fetcher.fetch(url)
    if not result.ok:
        log.warning("rankings fetch failed for %s: %s", date_str, result.status)
        return {"status": "error", "date": date_str, "error": str(result.status)}
    html_dir = out_dir / date_str
    html_dir.mkdir(parents=True, exist_ok=True)
    (html_dir / "ranking.html").write_text(result.html, encoding="utf-8")
    teams = parse_ranking_page(result.html)
    data = {"date": date_str, "url": url, "teams": teams, "scraped_at": datetime.now(timezone.utc).isoformat()}
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return {"status": "ok", "date": date_str, "teams_count": len(teams), "path": str(json_path)}


def scrape_rankings_range(
    fetcher: HltvFetcher,
    limiter: RateLimiter,
    config: ScraperConfig,
    start_date: date,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    if end_date is None:
        end_date = date.today()
    results = []
    current = _nearest_monday(start_date)
    while current <= end_date:
        if limiter.daily_cap_reached():
            break
        result = scrape_rankings(fetcher, limiter, config, current)
        results.append(result)
        current = date.fromordinal(current.toordinal() + 7)
    return results


def parse_ranking_page(html: str) -> list[dict[str, Any]]:
    try:
        from bs4 import BeautifulSoup
        return _parse_ranking_bs4(BeautifulSoup(html, "lxml"))
    except ImportError:
        return _parse_ranking_fallback(html)


def _parse_ranking_bs4(soup: Any) -> list[dict[str, Any]]:
    teams: list[dict[str, Any]] = []
    for item in soup.select(".ranked-team, .ranking-team, [class*='ranked']"):
        rank_el = item.select_one(".position, .ranking-number, [class*='position']")
        name_el = item.select_one(".name, .teamName, a[href*='/team/']")
        points_el = item.select_one(".points, [class*='points']")
        team_link = item.select_one("a[href*='/team/']")
        rank = _extract_int(rank_el.get_text(strip=True)) if rank_el else None
        name = name_el.get_text(strip=True) if name_el else None
        points = _extract_int(points_el.get_text(strip=True)) if points_el else None
        team_id = None
        if team_link:
            m = re.search(r"/team/(\d+)", team_link.get("href") or "")
            if m:
                team_id = m.group(1)
        if name:
            teams.append({"rank": rank, "team_hltv_id": team_id, "name": name, "points": points})
    if not teams:
        return _parse_ranking_fallback_from_soup(soup)
    return teams


def _parse_ranking_fallback_from_soup(soup: Any) -> list[dict[str, Any]]:
    return _parse_ranking_fallback(str(soup))


def _parse_ranking_fallback(html: str) -> list[dict[str, Any]]:
    teams: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in re.finditer(r'href="/team/(\d+)/([^"]+)"', html):
        team_id = m.group(1)
        name = m.group(2).replace("-", " ").strip()
        if team_id in seen:
            continue
        seen.add(team_id)
        context = html[max(0, m.start() - 300):m.start()]
        rank = None
        rank_m = re.search(r"#(\d+)", context)
        if rank_m:
            rank = int(rank_m.group(1))
        points = None
        pts_m = re.search(r"(\d+)\s*(?:points?|pts)", context, re.I)
        if pts_m:
            points = int(pts_m.group(1))
        teams.append({"rank": rank or (len(teams) + 1), "team_hltv_id": team_id, "name": name, "points": points})
    return teams


def _extract_int(text: str) -> int | None:
    m = re.search(r"\d+", text)
    return int(m.group(0)) if m else None


def _latest_monday() -> date:
    today = date.today()
    return date.fromordinal(today.toordinal() - today.weekday())


def _nearest_monday(d: date) -> date:
    return date.fromordinal(d.toordinal() - d.weekday())
