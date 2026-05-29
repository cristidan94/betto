from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - dependency installed in scraper venv.
    BeautifulSoup = None  # type: ignore[assignment]


def parse_results_page(html: str) -> list[dict[str, Any]]:
    if BeautifulSoup is None:
        return _parse_results_page_fallback(html)
    soup = _soup(html)
    entries: list[dict[str, Any]] = []
    for link in soup.select("a[href*='/matches/']"):
        href = link.get("href") or ""
        match = re.search(r"/matches/(\d+)/([^?#]+)", href)
        if not match:
            continue
        text = " ".join(link.get_text(" ", strip=True).split())
        entries.append(
            {
                "match_id": match.group(1),
                "match_url": href,
                "title": text,
                "event_name": _result_event_name(link),
                "event_stars": _result_stars(link),
                "scheduled_at": _result_datetime(link),
            }
        )
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for entry in entries:
        if entry["match_id"] not in seen:
            seen.add(entry["match_id"])
            unique.append(entry)
    return unique


def parse_match_page(html: str, match_id: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        return _parse_match_page_fallback(html, match_id)
    soup = _soup(html)
    teams = _teams(soup)
    maps = _maps(soup, teams)
    return {
        "hltv_id": match_id,
        "scheduled_at": _match_datetime(soup).isoformat(),
        "best_of": _best_of(soup, len(maps)),
        "status": "finished" if maps else "scheduled",
        "team_a": teams[0],
        "team_b": teams[1],
        "event": _event(soup),
        "players": _players(soup, teams),
        "maps": maps,
        "vetoes": _vetoes(soup, teams),
        "stats_url": _stats_url(soup, teams),
    }


def parse_stats_page(html: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        return _parse_stats_page_fallback(html)
    soup = _soup(html)
    players = []
    for row in soup.select("tr"):
        link = row.select_one("a[href*='/player/']")
        if not link:
            continue
        href = link.get("href") or ""
        match = re.search(r"/player/(\d+)", href)
        if match:
            players.append({"hltv_id": match.group(1), "nickname": link.get_text(strip=True)})
    return {"players": players}


def parse_map_stats_page(html: str) -> list[dict[str, Any]]:
    if BeautifulSoup is None:
        return _parse_map_stats_page_fallback(html)
    soup = _soup(html)
    rows: list[dict[str, Any]] = []
    for row in soup.select("tr"):
        link = row.select_one("a[href*='/player/']")
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        if not link or len(cells) < 2:
            continue
        href = link.get("href") or ""
        match = re.search(r"/player/(\d+)", href)
        rows.append({"player_hltv_id": match.group(1) if match else "", "nickname": link.get_text(strip=True), "cells": cells})
    return rows


def _soup(html: str):
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 is required for scraper parsing")
    return BeautifulSoup(html, "lxml")


def _parse_results_page_fallback(html: str) -> list[dict[str, Any]]:
    entries = []
    for href, text, start in _anchors(html):
        match = re.search(r"/matches/(\d+)/([^?#]+)", href)
        if not match:
            continue
        context = html[max(0, start - 500) : start]
        entries.append(
            {
                "match_id": match.group(1),
                "match_url": href,
                "title": text,
                "event_name": _event_name_from_context(context),
                "event_stars": _stars_from_context(context),
                "scheduled_at": None,
            }
        )
    return _unique_entries(entries)


def _parse_match_page_fallback(html: str, match_id: str) -> dict[str, Any]:
    teams = _fallback_teams(html)
    maps = _fallback_maps(html, teams)
    return {
        "hltv_id": match_id,
        "scheduled_at": _fallback_datetime(html).isoformat(),
        "best_of": _fallback_best_of(html, len(maps)),
        "status": "finished" if maps else "scheduled",
        "team_a": teams[0],
        "team_b": teams[1],
        "event": _fallback_event(html),
        "players": _fallback_players(html, teams),
        "maps": maps,
        "vetoes": _fallback_vetoes(html, teams),
        "stats_url": _fallback_stats_url(html),
    }


def _parse_stats_page_fallback(html: str) -> dict[str, Any]:
    players = []
    seen: set[str] = set()
    for href, text, _ in _anchors(html):
        match = re.search(r"/player/(\d+)", href)
        if match and match.group(1) not in seen:
            seen.add(match.group(1))
            players.append({"hltv_id": match.group(1), "nickname": text})
    return {"players": players}


def _parse_map_stats_page_fallback(html: str) -> list[dict[str, Any]]:
    rows = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, flags=re.I | re.S):
        players = _parse_stats_page_fallback(row)["players"]
        cells = [_strip_tags(cell).strip() for cell in re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.I | re.S)]
        if players and len(cells) >= 2:
            rows.append({"player_hltv_id": players[0]["hltv_id"], "nickname": players[0]["nickname"], "cells": cells})
    return rows


def _anchors(html: str) -> list[tuple[str, str, int]]:
    anchors = []
    pattern = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", flags=re.I | re.S)
    for match in pattern.finditer(html):
        href_match = re.search(r"""href\s*=\s*["']([^"']+)["']""", match.group("attrs"), flags=re.I)
        if not href_match:
            continue
        anchors.append((href_match.group(1), _strip_tags(match.group("body")).strip(), match.start()))
    return anchors


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def _unique_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique = []
    for entry in entries:
        if entry["match_id"] in seen:
            continue
        seen.add(entry["match_id"])
        unique.append(entry)
    return unique


def _event_name_from_context(context: str) -> str | None:
    matches = re.findall(r"""(?:event-name|eventName|event-title)["'\s=>:-]+([^<"']+)""", context, flags=re.I)
    if matches:
        return _strip_tags(matches[-1])
    text = _strip_tags(context)
    return text[-120:] if text else None


def _stars_from_context(context: str) -> int | None:
    explicit = re.findall(r"""(?:stars|event-stars)["'\s=>:-]+([1-5])""", context, flags=re.I)
    if explicit:
        return int(explicit[-1])
    stars = context.count("*")
    return stars or None


def _fallback_teams(html: str) -> tuple[dict[str, str], dict[str, str]]:
    teams = []
    for href, text, _ in _anchors(html):
        match = re.search(r"/team/(\d+)/([^?#]+)", href)
        if match and text:
            teams.append({"hltv_id": match.group(1), "name": text})
        if len(teams) == 2:
            return teams[0], teams[1]
    return {"hltv_id": "unknown-a", "name": "Team A"}, {"hltv_id": "unknown-b", "name": "Team B"}


def _fallback_players(html: str, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, str]]:
    players = []
    current_team = teams[0]["hltv_id"]
    seen: set[str] = set()
    for href, text, _ in _anchors(html):
        match = re.search(r"/player/(\d+)/([^?#]+)", href)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        players.append({"hltv_id": match.group(1), "nickname": text or match.group(2), "team_hltv_id": current_team})
        if len(players) == 5:
            current_team = teams[1]["hltv_id"]
    return players


def _fallback_maps(html: str, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    maps = []
    text = _strip_tags(html)
    map_stats_ids = _html_map_stats_ids(html)
    pattern = re.compile(
        r"(Mirage|Inferno|Nuke|Ancient|Anubis|Dust2|Train|Vertigo|Overpass|Cache|Cobblestone)"
        r".{0,80}?(\d{1,2})\s*[-:]\s*(\d{1,2})"
        r"(?:.{0,120}?mapstatsid/(\d+))?",
        re.I,
    )
    for index, match in enumerate(pattern.finditer(text), start=1):
        score_a, score_b = int(match.group(2)), int(match.group(3))
        maps.append(
            {
                "map_index": index,
                "map_name": _canonical_map(match.group(1)),
                "team_a_score": score_a,
                "team_b_score": score_b,
                "winner_hltv_id": teams[0]["hltv_id"] if score_a > score_b else teams[1]["hltv_id"],
                "map_stats_id": match.group(4) or (map_stats_ids[index - 1] if index - 1 < len(map_stats_ids) else None),
            }
        )
    return maps


def _fallback_vetoes(html: str, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    vetoes = []
    text = _strip_tags(html)
    pattern = re.compile(
        r"([^.;\n]*?(?:removed|picked|ban|pick)[^.;\n]*?"
        r"(Mirage|Inferno|Nuke|Ancient|Anubis|Dust2|Train|Vertigo|Overpass|Cache|Cobblestone)[^.;\n]*)",
        re.I,
    )
    for index, match in enumerate(pattern.finditer(text), start=1):
        line = match.group(1)
        action = "pick" if re.search(r"picked|pick", line, re.I) else "ban"
        team_id = None
        if teams[0]["name"].lower() in line.lower():
            team_id = teams[0]["hltv_id"]
        elif teams[1]["name"].lower() in line.lower():
            team_id = teams[1]["hltv_id"]
        vetoes.append({"order_idx": index, "team_hltv_id": team_id, "action": action, "map_name": _canonical_map(match.group(2))})
    return vetoes


def _fallback_event(html: str) -> dict[str, Any]:
    for href, text, _ in _anchors(html):
        match = re.search(r"/events/(\d+)", href)
        if match:
            return {"hltv_id": match.group(1), "name": text, "stars": None}
    return {"hltv_id": "unknown", "name": "Unknown Event", "stars": None}


def _fallback_datetime(html: str) -> datetime:
    match = re.search(r"""data-unix\s*=\s*["'](\d+)["']""", html, flags=re.I)
    if match:
        value = float(match.group(1))
        if value > 10_000_000_000:
            value /= 1000
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _fallback_stats_url(html: str) -> str | None:
    for href, _, _ in _anchors(html):
        if "/stats/matches/" in href:
            return href if href.startswith("http") else f"https://www.hltv.org{href}"
    return None


def _fallback_best_of(html: str, map_count: int) -> int:
    match = re.search(r"Best of\s*(\d+)|bo\s*(\d+)", _strip_tags(html), re.I)
    if match:
        return int(match.group(1) or match.group(2))
    return map_count if map_count % 2 == 1 and map_count else 1


def _canonical_map(value: str) -> str:
    normalized = value.lower()
    return "Dust2" if normalized == "dust2" else value.title()


def _html_map_stats_ids(html: str) -> list[str]:
    return re.findall(r"mapstatsid/(\d+)", html)


def _teams(soup) -> tuple[dict[str, str], dict[str, str]]:
    teams = []
    for link in soup.select("a[href*='/team/']"):
        href = link.get("href") or ""
        match = re.search(r"/team/(\d+)/([^?#]+)", href)
        name = link.get_text(" ", strip=True)
        if match and name:
            teams.append({"hltv_id": match.group(1), "name": name})
        if len(teams) >= 2:
            return teams[0], teams[1]
    return {"hltv_id": "unknown-a", "name": "Team A"}, {"hltv_id": "unknown-b", "name": "Team B"}


def _players(soup, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, str]]:
    lineup_players = _lineup_players(soup)
    if lineup_players:
        return lineup_players

    players = []
    seen: set[str] = set()
    current_team = teams[0]["hltv_id"]
    for link in soup.select("a[href*='/player/']"):
        href = link.get("href") or ""
        match = re.search(r"/player/(\d+)/([^?#]+)", href)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        text = link.get_text(" ", strip=True)
        nickname = text if text and "profile" not in text.lower() else match.group(2)
        players.append({"hltv_id": match.group(1), "nickname": nickname, "team_hltv_id": current_team})
        if len(players) == 5:
            current_team = teams[1]["hltv_id"]
    return players


def _lineup_players(soup) -> list[dict[str, str]]:
    container = soup.select_one(".lineups-compare-container[data-team1-players-data], .lineups-compare-container[data-team2-players-data]")
    if not container:
        return []
    players: list[dict[str, str]] = []
    for attr in ("data-team1-players-data", "data-team2-players-data"):
        raw = container.get(attr)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for player_id, row in payload.items():
            players.append(
                {
                    "hltv_id": str(row.get("playerId") or player_id),
                    "nickname": str(row.get("nickname") or player_id),
                    "team_hltv_id": str(row.get("teamId") or ""),
                }
            )
    return players


def _maps(soup, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    maps = []
    text = soup.get_text("\n", strip=True)
    map_stats_ids = _soup_map_stats_ids(soup)
    pattern = re.compile(r"(Mirage|Inferno|Nuke|Ancient|Anubis|Dust2|Train|Vertigo|Overpass|Cache|Cobblestone).*?(\d{1,2})\s*[-:]\s*(\d{1,2})", re.I)
    for index, match in enumerate(pattern.finditer(text), start=1):
        score_a, score_b = int(match.group(2)), int(match.group(3))
        maps.append(
            {
                "map_index": index,
                "map_name": match.group(1).title().replace("Dust2", "Dust2"),
                "team_a_score": score_a,
                "team_b_score": score_b,
                "winner_hltv_id": teams[0]["hltv_id"] if score_a > score_b else teams[1]["hltv_id"],
                "map_stats_id": map_stats_ids[index - 1] if index - 1 < len(map_stats_ids) else _map_stats_id_near(match.group(0)),
            }
        )
    return maps


def _soup_map_stats_ids(soup) -> list[str]:
    ids = []
    for link in soup.select("a[href*='mapstatsid/']"):
        href = link.get("href") or ""
        match = re.search(r"mapstatsid/(\d+)", href)
        if match:
            ids.append(match.group(1))
    return ids


def _vetoes(soup, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    vetoes = []
    for index, item in enumerate(soup.find_all(string=re.compile(r"\b(removed|picked|ban|pick)\b", re.I)), start=1):
        text = str(item)
        map_match = re.search(r"(Mirage|Inferno|Nuke|Ancient|Anubis|Dust2|Train|Vertigo|Overpass|Cache|Cobblestone)", text, re.I)
        action = "pick" if re.search(r"picked|pick", text, re.I) else "ban"
        if map_match:
            team_id = teams[0]["hltv_id"] if teams[0]["name"].lower() in text.lower() else None
            if team_id is None and teams[1]["name"].lower() in text.lower():
                team_id = teams[1]["hltv_id"]
            vetoes.append({"order_idx": index, "team_hltv_id": team_id, "action": action, "map_name": map_match.group(1)})
    return vetoes


def _event(soup) -> dict[str, Any]:
    link = soup.select_one(".matchSidebarEventHeader[href*='/events/']") or soup.select_one("a[href*='/events/']:has(.matchSidebarEventName)")
    if link is None:
        for candidate in soup.select("a[href*='/events/']"):
            href = candidate.get("href") or ""
            text = candidate.get_text(" ", strip=True)
            if "/events/archive" not in href and text and text.lower() != "archive":
                link = candidate
                break
    if not link:
        return {"hltv_id": "unknown", "name": "Unknown Event", "stars": None}
    href = link.get("href") or ""
    match = re.search(r"/events/(\d+)", href)
    return {"hltv_id": match.group(1) if match else "unknown", "name": link.get_text(" ", strip=True), "stars": None}


def _best_of(soup, map_count: int) -> int:
    text = soup.get_text(" ", strip=True)
    match = re.search(r"Best of\s*(\d+)|bo\s*(\d+)", text, re.I)
    if match:
        return int(match.group(1) or match.group(2))
    return map_count if map_count % 2 == 1 and map_count else 1


def _match_datetime(soup) -> datetime:
    node = soup.select_one("[data-unix]")
    if node and node.get("data-unix"):
        value = float(node.get("data-unix"))
        if value > 10_000_000_000:
            value /= 1000
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _stats_url(soup, teams: tuple[dict[str, str], dict[str, str]]) -> str | None:
    team_slugs = [_slugify_team(team["name"]) for team in teams]
    for link in soup.select("a[href*='/stats/matches/']"):
        href = link.get("href") or ""
        if not href:
            continue
        lowered = href.lower()
        if all(slug and slug in lowered for slug in team_slugs):
            return href if href.startswith("http") else f"https://www.hltv.org{href}"
    return None


def _slugify_team(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _nearby_event(link) -> str | None:
    parent = link.find_parent()
    return parent.get_text(" ", strip=True)[:120] if parent else None


def _result_event_name(link) -> str | None:
    title = link.get("title")
    if title:
        return str(title).strip()
    parent = link.find_parent()
    event = parent.select_one(".event-name, .eventName, .matchEventName") if parent else None
    if event:
        return event.get_text(" ", strip=True)
    return _nearby_event(link)


def _result_stars(link) -> int | None:
    target = link.select_one("[stars]") or (link.find_parent().select_one("[stars]") if link.find_parent() else None)
    if target and target.get("stars"):
        try:
            return int(target.get("stars"))
        except (TypeError, ValueError):
            return None
    return _stars_near(link)


def _result_datetime(link) -> str | None:
    node = link.select_one("[data-unix]")
    if not node or not node.get("data-unix"):
        return None
    value = float(node.get("data-unix"))
    if value > 10_000_000_000:
        value /= 1000
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _stars_near(link) -> int | None:
    text = _nearby_event(link) or ""
    count = text.count("*")
    return count or None


def _map_stats_id_near(text: str) -> str | None:
    match = re.search(r"mapstatsid/(\d+)|statsid[=/](\d+)", text)
    return match.group(1) or match.group(2) if match else None


# ---------------------------------------------------------------------------
# Entity page parsers (event, team, player)
# ---------------------------------------------------------------------------


def parse_event_page(html: str, event_id: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        return _parse_event_page_fallback(html, event_id)
    soup = _soup(html)
    text = soup.get_text(" ", strip=True)
    return {
        "hltv_id": event_id,
        "name": _event_page_name(soup),
        "location": _event_page_location(soup, text),
        "country": _event_page_country(soup, text),
        "lan": _event_page_lan(soup, text),
        "prize_pool": _event_page_prize(soup, text),
        "team_count": _event_page_team_count(soup, text),
        "format": _event_page_format(soup, text),
        "dates": _event_page_dates(soup, text),
        "teams": _event_page_teams(soup),
    }


def parse_team_page(html: str, team_id: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        return _parse_team_page_fallback(html, team_id)
    soup = _soup(html)
    text = soup.get_text(" ", strip=True)
    return {
        "hltv_id": team_id,
        "name": _team_page_name(soup),
        "country": _team_page_country(soup, text),
        "world_ranking": _team_page_ranking(soup, text),
        "coach": _team_page_coach(soup),
        "roster": _team_page_roster(soup),
        "map_stats": _team_page_map_stats(soup, text),
    }


def parse_player_page(html: str, player_id: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        return _parse_player_page_fallback(html, player_id)
    soup = _soup(html)
    text = soup.get_text(" ", strip=True)
    return {
        "hltv_id": player_id,
        "nickname": _player_page_nickname(soup),
        "real_name": _player_page_real_name(soup, text),
        "country": _player_page_country(soup, text),
        "age": _player_page_age(soup, text),
        "team": _player_page_team(soup),
        "rating": _player_page_stat(text, r"(?:Rating|rating)\s*[\d.]+\s*([\d.]+)"),
        "dpr": _player_page_stat(text, r"DPR\s*([\d.]+)"),
        "kast": _player_page_stat(text, r"KAST\s*([\d.]+)"),
        "impact": _player_page_stat(text, r"Impact\s*([\d.]+)"),
        "adr": _player_page_stat(text, r"ADR\s*([\d.]+)"),
        "kpr": _player_page_stat(text, r"KPR\s*([\d.]+)"),
        "headshot_pct": _player_page_stat(text, r"(?:HS|Headshot)\s*%?\s*([\d.]+)"),
        "maps_played": _player_page_int_stat(text, r"Maps\s*played\s*(\d+)"),
    }


# -- Event page helpers --


def _event_page_name(soup) -> str:
    el = soup.select_one(".event-hub-title, .eventname, h1.event-name")
    if el:
        return el.get_text(" ", strip=True)
    title = soup.select_one("title")
    if title:
        return title.get_text(" ", strip=True).split("|")[0].strip()
    return "Unknown Event"


def _event_page_location(soup, text: str) -> str | None:
    el = soup.select_one(".flag-align .text-ellipsis, .event-meta-value, .location")
    if el:
        return el.get_text(" ", strip=True)
    match = re.search(r"(?:Location|Venue)\s*[:\-]\s*([^\n|]+)", text, re.I)
    return match.group(1).strip() if match else None


def _event_page_country(soup, text: str) -> str | None:
    flag = soup.select_one(".event-world-ranking .flag, .flag-align .flag")
    if flag:
        title = flag.get("alt") or flag.get("title")
        if title:
            return str(title).strip()
    match = re.search(r"(?:Country|Location)\s*[:\-]\s*([A-Za-z ]+)", text, re.I)
    return match.group(1).strip() if match else None


def _event_page_lan(soup, text: str) -> bool | None:
    if re.search(r"\bLAN\b", text):
        return True
    if re.search(r"\bOnline\b", text, re.I):
        return False
    return None


def _event_page_prize(soup, text: str) -> str | None:
    el = soup.select_one(".prizepool, .prize-pool")
    if el:
        return el.get_text(" ", strip=True)
    match = re.search(r"(?:Prize\s*pool|Prizepool)\s*[:\-]?\s*(\$[\d,]+(?:\.\d+)?)", text, re.I)
    return match.group(1) if match else None


def _event_page_team_count(soup, text: str) -> int | None:
    el = soup.select_one(".teamsNumber")
    if el:
        try:
            return int(re.sub(r"\D", "", el.get_text()))
        except ValueError:
            pass
    match = re.search(r"(\d+)\s*teams", text, re.I)
    return int(match.group(1)) if match else None


def _event_page_format(soup, text: str) -> str | None:
    el = soup.select_one(".format-value, .event-meta-value")
    if el:
        return el.get_text(" ", strip=True)[:200]
    match = re.search(r"Format\s*[:\-]\s*([^\n|]+)", text, re.I)
    return match.group(1).strip()[:200] if match else None


def _event_page_dates(soup, text: str) -> dict[str, str | None]:
    dates: dict[str, str | None] = {"start": None, "end": None}
    for node in soup.select("[data-unix]"):
        val = node.get("data-unix")
        if val:
            try:
                ts = float(val)
                if ts > 10_000_000_000:
                    ts /= 1000
                iso = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                if dates["start"] is None or iso < dates["start"]:
                    dates["start"] = iso
                if dates["end"] is None or iso > dates["end"]:
                    dates["end"] = iso
            except (ValueError, OverflowError):
                pass
    return dates


def _event_page_teams(soup) -> list[dict[str, str]]:
    teams: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in soup.select("a[href*='/team/']"):
        href = link.get("href") or ""
        match = re.search(r"/team/(\d+)/([^?#]+)", href)
        name = link.get_text(" ", strip=True)
        if match and name and match.group(1) not in seen:
            seen.add(match.group(1))
            teams.append({"hltv_id": match.group(1), "name": name})
    return teams


def _parse_event_page_fallback(html: str, event_id: str) -> dict[str, Any]:
    text = _strip_tags(html)
    teams = []
    seen: set[str] = set()
    for href, name, _ in _anchors(html):
        m = re.search(r"/team/(\d+)/([^?#]+)", href)
        if m and name and m.group(1) not in seen:
            seen.add(m.group(1))
            teams.append({"hltv_id": m.group(1), "name": name})
    return {
        "hltv_id": event_id,
        "name": _event_name_from_context(text) or "Unknown Event",
        "location": None,
        "country": None,
        "lan": True if re.search(r"\bLAN\b", text) else None,
        "prize_pool": None,
        "team_count": None,
        "format": None,
        "dates": {"start": None, "end": None},
        "teams": teams,
    }


# -- Team page helpers --


def _team_page_name(soup) -> str:
    el = soup.select_one(".profile-team-name, h1.team-name, .team-name")
    if el:
        return el.get_text(" ", strip=True)
    title = soup.select_one("title")
    if title:
        return title.get_text(" ", strip=True).split("|")[0].strip()
    return "Unknown Team"


def _team_page_country(soup, text: str) -> str | None:
    flag = soup.select_one(".team-country .flag, .profile-team-info .flag")
    if flag:
        title = flag.get("alt") or flag.get("title")
        if title:
            return str(title).strip()
    return None


def _team_page_ranking(soup, text: str) -> int | None:
    el = soup.select_one(".profile-team-stat .right, .ranking .right")
    if el:
        match = re.search(r"#?(\d+)", el.get_text())
        if match:
            return int(match.group(1))
    match = re.search(r"(?:World\s*ranking|Ranking)\s*#?(\d+)", text, re.I)
    return int(match.group(1)) if match else None


def _team_page_coach(soup) -> dict[str, str] | None:
    el = soup.select_one(".profile-team-coach a[href*='/player/']")
    if not el:
        return None
    href = el.get("href") or ""
    match = re.search(r"/player/(\d+)", href)
    return {"hltv_id": match.group(1) if match else "", "nickname": el.get_text(" ", strip=True)}


def _team_page_roster(soup) -> list[dict[str, str]]:
    players: list[dict[str, str]] = []
    seen: set[str] = set()
    for container in soup.select(".players-table, .bodyshot-team, .team-roster"):
        for link in container.select("a[href*='/player/']"):
            href = link.get("href") or ""
            match = re.search(r"/player/(\d+)/([^?#]+)", href)
            if match and match.group(1) not in seen:
                seen.add(match.group(1))
                players.append({
                    "hltv_id": match.group(1),
                    "nickname": link.get_text(" ", strip=True) or match.group(2),
                })
    if not players:
        for link in soup.select("a[href*='/player/']"):
            href = link.get("href") or ""
            match = re.search(r"/player/(\d+)/([^?#]+)", href)
            name = link.get_text(" ", strip=True)
            if match and name and match.group(1) not in seen:
                seen.add(match.group(1))
                players.append({"hltv_id": match.group(1), "nickname": name})
            if len(players) >= 7:
                break
    return players


def _team_page_map_stats(soup, text: str) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    map_names = {"Mirage", "Inferno", "Nuke", "Ancient", "Anubis", "Dust2", "Train", "Vertigo", "Overpass", "Cache"}
    for map_name in map_names:
        pattern = re.compile(rf"{map_name}\s+(\d+)\s+/\s+(\d+)", re.I)
        match = pattern.search(text)
        if match:
            wins = int(match.group(1))
            total = int(match.group(2))
            stats.append({
                "map_name": map_name,
                "wins": wins,
                "losses": total - wins,
                "total": total,
                "win_rate": round(wins / total, 3) if total > 0 else 0.0,
            })
    return stats


def _parse_team_page_fallback(html: str, team_id: str) -> dict[str, Any]:
    text = _strip_tags(html)
    players: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, name, _ in _anchors(html):
        m = re.search(r"/player/(\d+)/([^?#]+)", href)
        if m and name and m.group(1) not in seen:
            seen.add(m.group(1))
            players.append({"hltv_id": m.group(1), "nickname": name})
    rank_match = re.search(r"(?:World\s*ranking|Ranking)\s*#?(\d+)", text, re.I)
    return {
        "hltv_id": team_id,
        "name": _fallback_team_name(html),
        "country": None,
        "world_ranking": int(rank_match.group(1)) if rank_match else None,
        "coach": None,
        "roster": players[:7],
        "map_stats": [],
    }


def _fallback_team_name(html: str) -> str:
    match = re.search(r"<title[^>]*>([^<]+)", html, re.I)
    if match:
        return match.group(1).split("|")[0].strip()
    return "Unknown Team"


# -- Player page helpers --


def _player_page_nickname(soup) -> str:
    el = soup.select_one(".playerNickname, h1.player-nick, .player-nick")
    if el:
        return el.get_text(" ", strip=True)
    title = soup.select_one("title")
    if title:
        return title.get_text(" ", strip=True).split("|")[0].strip()
    return "Unknown"


def _player_page_real_name(soup, text: str) -> str | None:
    el = soup.select_one(".playerRealname, .player-realname")
    if el:
        name = el.get_text(" ", strip=True)
        return name if name else None
    return None


def _player_page_country(soup, text: str) -> str | None:
    flag = soup.select_one(".playerRealname .flag, .player-realname .flag")
    if flag:
        title = flag.get("alt") or flag.get("title")
        if title:
            return str(title).strip()
    return None


def _player_page_age(soup, text: str) -> int | None:
    el = soup.select_one(".playerAge .listRight")
    if el:
        match = re.search(r"(\d+)", el.get_text())
        if match:
            return int(match.group(1))
    match = re.search(r"Age\s*[:\-]?\s*(\d+)", text, re.I)
    return int(match.group(1)) if match else None


def _player_page_team(soup) -> dict[str, str] | None:
    link = soup.select_one(".playerTeam a[href*='/team/'], a.team-name[href*='/team/']")
    if not link:
        for candidate in soup.select("a[href*='/team/']"):
            href = candidate.get("href") or ""
            if "/team/" in href and "/teams/" not in href:
                link = candidate
                break
    if not link:
        return None
    href = link.get("href") or ""
    match = re.search(r"/team/(\d+)/([^?#]+)", href)
    return {"hltv_id": match.group(1) if match else "", "name": link.get_text(" ", strip=True)}


def _player_page_stat(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, re.I)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _player_page_int_stat(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.I)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _parse_player_page_fallback(html: str, player_id: str) -> dict[str, Any]:
    text = _strip_tags(html)
    team = None
    for href, name, _ in _anchors(html):
        m = re.search(r"/team/(\d+)/([^?#]+)", href)
        if m and name:
            team = {"hltv_id": m.group(1), "name": name}
            break
    return {
        "hltv_id": player_id,
        "nickname": _fallback_player_nickname(html),
        "real_name": None,
        "country": None,
        "age": None,
        "team": team,
        "rating": _player_page_stat(text, r"(?:Rating|rating)\s*[\d.]+\s*([\d.]+)"),
        "dpr": None,
        "kast": None,
        "impact": None,
        "adr": _player_page_stat(text, r"ADR\s*([\d.]+)"),
        "kpr": None,
        "headshot_pct": None,
        "maps_played": None,
    }


def _fallback_player_nickname(html: str) -> str:
    match = re.search(r"<title[^>]*>([^<]+)", html, re.I)
    if match:
        return match.group(1).split("|")[0].strip()
    return "Unknown"
