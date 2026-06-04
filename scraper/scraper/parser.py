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


def parse_upcoming_page(html: str) -> list[dict[str, Any]]:
    if BeautifulSoup is None:
        return _parse_upcoming_page_fallback(html)
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
                "is_live": _is_live_match(link),
            }
        )
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for entry in entries:
        if entry["match_id"] not in seen:
            seen.add(entry["match_id"])
            unique.append(entry)
    return unique


def _is_live_match(link) -> bool:
    parent = link.find_parent()
    if parent:
        text = parent.get_text(" ", strip=True).lower()
        if "live" in text:
            return True
        if parent.select_one(".live-flag, .livescore, [class*=live]"):
            return True
    return False


def _parse_upcoming_page_fallback(html: str) -> list[dict[str, Any]]:
    entries = []
    text_lower = html.lower()
    for href, text, start in _anchors(html):
        match = re.search(r"/matches/(\d+)/([^?#]+)", href)
        if not match:
            continue
        context = html[max(0, start - 500): start]
        entries.append(
            {
                "match_id": match.group(1),
                "match_url": href,
                "title": text,
                "event_name": _event_name_from_context(context),
                "event_stars": _stars_from_context(context),
                "scheduled_at": None,
                "is_live": "live" in context.lower(),
            }
        )
    return _unique_entries(entries)


def parse_match_page(html: str, match_id: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        return _parse_match_page_fallback(html, match_id)
    soup = _soup(html)
    teams = _teams(soup)
    maps = _maps(soup, teams)
    return {
        "hltv_id": match_id,
        "scheduled_at": _match_datetime(soup).isoformat(),
        "best_of": _best_of(soup, maps),
        "status": "finished" if maps else "scheduled",
        "team_a": teams[0],
        "team_b": teams[1],
        "event": _event(soup),
        "players": _players(soup, teams, maps),
        "maps": maps,
        "vetoes": _vetoes(soup, teams),
        "stats_url": _stats_url(soup, teams),
        "match_stage": _match_stage(soup),
        "head_to_head": _head_to_head(soup, teams),
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
    team_hltv_id = ""
    for table in soup.select("table"):
        header = table.find_previous(["a", "div", "span"], href=re.compile(r"/team/\d+")) if table else None
        if header:
            m = re.search(r"/team/(\d+)", header.get("href") or "")
            if m:
                team_hltv_id = m.group(1)
        for row in table.select("tr"):
            link = row.select_one("a[href*='/player/']")
            cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
            if not link or len(cells) < 2:
                continue
            href = link.get("href") or ""
            match = re.search(r"/player/(\d+)", href)
            rows.append({
                "player_hltv_id": match.group(1) if match else "",
                "nickname": link.get_text(strip=True),
                "team_hltv_id": team_hltv_id,
                "cells": cells,
            })
    _merge_side_stats(soup, rows)
    return rows


def _merge_side_stats(soup, rows: list[dict[str, Any]]) -> None:
    side_tables = soup.select(".stats-table")
    if not side_tables:
        return
    ct_data: dict[str, dict] = {}
    t_data: dict[str, dict] = {}
    for table in side_tables:
        heading = table.find_previous(string=re.compile(r"\b(CT|T)\s*side", re.I))
        if not heading:
            container = table.find_parent(class_=re.compile(r"ct|terrorist", re.I))
            if container:
                cls = " ".join(container.get("class", []))
                heading = "CT side" if "ct" in cls.lower() else "T side"
        if not heading:
            continue
        side_label = "ct" if "ct" in str(heading).lower() else "t"
        target = ct_data if side_label == "ct" else t_data
        for tr in table.select("tr"):
            link = tr.select_one("a[href*='/player/']")
            cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if not link or len(cells) < 2:
                continue
            href = link.get("href") or ""
            m = re.search(r"/player/(\d+)", href)
            if m:
                kd = _extract_kd_from_cells(cells)
                target[m.group(1)] = kd
    for row in rows:
        pid = row.get("player_hltv_id")
        if pid and pid in ct_data:
            row["ct_kills"] = ct_data[pid].get("kills")
            row["ct_deaths"] = ct_data[pid].get("deaths")
        if pid and pid in t_data:
            row["t_kills"] = t_data[pid].get("kills")
            row["t_deaths"] = t_data[pid].get("deaths")


def _extract_kd_from_cells(cells: list) -> dict[str, int | None]:
    for cell in cells[1:4]:
        text = str(cell)
        m = re.search(r"(\d+)\s*[-/]\s*(\d+)", text)
        if m:
            return {"kills": int(m.group(1)), "deaths": int(m.group(2))}
    kills = None
    deaths = None
    for i, cell in enumerate(cells[1:4], start=1):
        try:
            val = int(str(cell).strip().split()[0])
            if kills is None:
                kills = val
            elif deaths is None:
                deaths = val
                break
        except (ValueError, IndexError):
            continue
    return {"kills": kills, "deaths": deaths}


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
        "best_of": _fallback_best_of(html, maps),
        "status": "finished" if maps else "scheduled",
        "team_a": teams[0],
        "team_b": teams[1],
        "event": _fallback_event(html),
        "players": _fallback_players(html, teams),
        "maps": maps,
        "vetoes": _fallback_vetoes(html, teams),
        "stats_url": _fallback_stats_url(html),
        "match_stage": None,
        "head_to_head": None,
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
            return {"hltv_id": match.group(1), "name": text, "stars": _stars_from_context(html)}
    return {"hltv_id": "unknown", "name": "Unknown Event", "stars": _stars_from_context(html)}


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


def _results_floor(maps: list[dict[str, Any]] | None) -> int:
    """Minimum best_of a finished series proves: a team that won W maps must
    have played at least a Bo(2W-1), so a 2-0 sweep cannot be a Bo1."""
    wins_a = wins_b = 0
    for item in maps or []:
        if not isinstance(item, dict):
            continue
        try:
            score_a = int(item.get("team_a_score"))
            score_b = int(item.get("team_b_score"))
        except (TypeError, ValueError):
            continue
        if score_a > score_b:
            wins_a += 1
        elif score_b > score_a:
            wins_b += 1
    top = max(wins_a, wins_b)
    return 2 * top - 1 if top else 0


def _resolve_best_of(text: str, maps: list[dict[str, Any]]) -> int:
    match = re.search(r"Best of\s*(\d+)|bo\s*(\d+)", text, re.I)
    parsed = int(match.group(1) or match.group(2)) if match else 0
    floor = _results_floor(maps)
    # Trust an explicit "Best of N" but never report fewer maps than the
    # results prove; when the page omits it, fall back to the results floor,
    # then to the odd-map-count heuristic for unplayed/edge cases.
    if parsed or floor:
        return max(parsed, floor)
    map_count = len(maps)
    return map_count if map_count % 2 == 1 and map_count else 1


def _fallback_best_of(html: str, maps: list[dict[str, Any]]) -> int:
    return _resolve_best_of(_strip_tags(html), maps)


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


def _players(
    soup,
    teams: tuple[dict[str, str], dict[str, str]],
    maps: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    lineup_players = _lineup_players(soup)
    if lineup_players:
        return lineup_players

    # For finished matches there is no lineup widget, but the embedded scoreboard
    # gives us the exact roster with correct team assignments — far more accurate
    # than scraping every /player/ link on the page (which also picks up the
    # head-to-head and sidebar sections).
    if maps:
        from_maps = _players_from_maps(maps)
        if from_maps:
            return from_maps

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


def _players_from_maps(maps: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for item in maps:
        for stat in item.get("player_stats") or []:
            pid = str(stat.get("player_hltv_id") or "")
            if pid and pid not in seen:
                seen[pid] = {
                    "hltv_id": pid,
                    "nickname": str(stat.get("nickname") or pid),
                    "team_hltv_id": str(stat.get("team_hltv_id") or ""),
                }
    return list(seen.values())


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


_MAP_NAMES = (
    "Mirage", "Inferno", "Nuke", "Ancient", "Anubis", "Dust2", "Train",
    "Vertigo", "Overpass", "Cache", "Cobblestone",
)


def _maps(soup, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    holders = soup.select(".mapholder")
    if holders:
        maps = _maps_from_holders(holders, teams)
        if maps:
            _attach_embedded_player_stats(soup, maps)
            return maps
    maps = _maps_from_text(soup, teams)
    _attach_embedded_player_stats(soup, maps)
    return maps


def _maps_from_holders(holders, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    maps: list[dict[str, Any]] = []
    index = 0
    for holder in holders:
        name_el = holder.select_one(".mapname")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if not name or name.lower() in {"tba", "default", "tbd"}:
            continue
        scores = [
            int(el.get_text(strip=True))
            for el in holder.select(".results-team-score")
            if el.get_text(strip=True).isdigit()
        ]
        if len(scores) < 2:
            # Map listed (veto) but not played yet — skip it.
            continue
        score_a, score_b = scores[0], scores[1]
        stats_id = None
        link = holder.select_one("a[href*='mapstatsid/']")
        if link:
            m = re.search(r"mapstatsid/(\d+)", link.get("href") or "")
            stats_id = m.group(1) if m else None
        winner = _holder_winner(holder, teams, score_a, score_b)
        halves = _half_scores_from_holder(holder, score_a, score_b)
        index += 1
        maps.append(
            {
                "map_index": index,
                "map_name": name.title() if name.lower() != "dust2" else "Dust2",
                "team_a_score": score_a,
                "team_b_score": score_b,
                "winner_hltv_id": winner,
                "map_stats_id": stats_id,
                **halves,
            }
        )
    return maps


def _holder_winner(holder, teams: tuple[dict[str, str], dict[str, str]], score_a: int, score_b: int) -> str:
    left = holder.select_one(".results-left")
    right = holder.select_one(".results-right")
    if left is not None and "won" in (left.get("class") or []):
        return teams[0]["hltv_id"]
    if right is not None and "won" in (right.get("class") or []):
        return teams[1]["hltv_id"]
    return teams[0]["hltv_id"] if score_a > score_b else teams[1]["hltv_id"]


def _half_scores_from_holder(holder, total_a: int, total_b: int) -> dict[str, Any]:
    half_el = holder.select_one(".results-center-half-score")
    if half_el:
        pairs = re.findall(r"(\d+)\s*:\s*(\d+)", half_el.get_text(" ", strip=True))
        if len(pairs) >= 2:
            h1_a, h1_b = int(pairs[0][0]), int(pairs[0][1])
            h2_a, h2_b = int(pairs[1][0]), int(pairs[1][1])
            return {
                "team_a_first_half": h1_a,
                "team_b_first_half": h1_b,
                "team_a_second_half": h2_a,
                "team_b_second_half": h2_b,
                "overtime": len(pairs) > 2 or (total_a + total_b) > 30,
            }
    return {
        "team_a_first_half": None,
        "team_b_first_half": None,
        "team_a_second_half": None,
        "team_b_second_half": None,
        "overtime": (total_a + total_b) > 30,
    }


def _maps_from_text(soup, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    maps = []
    text = soup.get_text("\n", strip=True)
    map_stats_ids = _soup_map_stats_ids(soup)
    pattern = re.compile(r"(" + "|".join(_MAP_NAMES) + r").*?(\d{1,2})\s*[-:]\s*(\d{1,2})", re.I)
    for index, match in enumerate(pattern.finditer(text), start=1):
        score_a, score_b = int(match.group(2)), int(match.group(3))
        after = text[match.end():match.end() + 200]
        halves = _parse_half_scores(after, score_a, score_b)
        maps.append(
            {
                "map_index": index,
                "map_name": match.group(1).title().replace("Dust2", "Dust2"),
                "team_a_score": score_a,
                "team_b_score": score_b,
                "winner_hltv_id": teams[0]["hltv_id"] if score_a > score_b else teams[1]["hltv_id"],
                "map_stats_id": map_stats_ids[index - 1] if index - 1 < len(map_stats_ids) else _map_stats_id_near(match.group(0)),
                **halves,
            }
        )
    return maps


def _attach_embedded_player_stats(soup, maps: list[dict[str, Any]]) -> None:
    """Attach per-player stats that HLTV embeds in the match page's #matchstats
    tabs (one tab per map, keyed by map-stats-id). This is the primary source of
    map player stats and avoids the heavily-challenged /stats/ pages."""
    if not maps:
        return
    embedded = _embedded_map_stats(soup)
    if not embedded:
        return
    for item in maps:
        stats_id = item.get("map_stats_id")
        rows = embedded.get(str(stats_id)) if stats_id else None
        if rows:
            item["player_stats"] = rows
    # Best-of-1 pages sometimes only render the aggregate "all" tab.
    if len(maps) == 1 and not maps[0].get("player_stats") and embedded.get("all"):
        maps[0]["player_stats"] = embedded["all"]


def _embedded_map_stats(soup) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for tab in soup.select("div.stats-content"):
        tab_id = tab.get("id") or ""
        m = re.match(r"(\d+|all)-content$", tab_id)
        if not m:
            continue
        key = m.group(1)
        rows = _player_rows_from_stat_tables(tab.select("table.totalstats"))
        if rows:
            # HLTV embeds CT-only and T-only scoreboards alongside the "all"
            # table (hidden in the page, toggled client-side). Merge their
            # per-player kill/death splits into the combined rows.
            by_id = {row["player_hltv_id"]: row for row in rows}
            _merge_side_kills(tab.select("table.ctstats"), by_id, "ct")
            _merge_side_kills(tab.select("table.tstats"), by_id, "t")
            result[key] = rows
    return result


def _merge_side_kills(tables, by_id: dict[str, dict[str, Any]], side: str) -> None:
    for table in tables:
        col_map = _stat_column_map(table)
        kd_index = col_map.get("kd")
        if kd_index is None:
            continue
        for tr in table.select("tr"):
            player_link = tr.select_one("a[href*='/player/']")
            if not player_link:
                continue
            pm = re.search(r"/player/(\d+)", player_link.get("href") or "")
            if not pm or pm.group(1) not in by_id:
                continue
            cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if kd_index >= len(cells):
                continue
            kd = re.search(r"(\d+)\s*-\s*(\d+)", cells[kd_index])
            if kd:
                by_id[pm.group(1)][f"{side}_kills"] = int(kd.group(1))
                by_id[pm.group(1)][f"{side}_deaths"] = int(kd.group(2))


def _player_rows_from_stat_tables(tables) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in tables:
        team_id = ""
        team_link = table.find("a", href=re.compile(r"/team/\d+"))
        if team_link:
            tm = re.search(r"/team/(\d+)", team_link.get("href") or "")
            team_id = tm.group(1) if tm else ""
        col_map = _stat_column_map(table)
        for tr in table.select("tr"):
            player_link = tr.select_one("a[href*='/player/']")
            if not player_link:
                continue
            pm = re.search(r"/player/(\d+)(?:/([^/?#]+))?", player_link.get("href") or "")
            if not pm:
                continue
            cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if len(cells) < 2:
                continue
            stat = {
                "player_hltv_id": pm.group(1),
                "nickname": pm.group(2) or player_link.get_text(strip=True),
                "team_hltv_id": team_id,
            }
            stat.update(_stat_values_from_cells(cells, col_map))
            rows.append(stat)
    return rows


def _stat_column_map(table) -> dict[str, int]:
    header = table.select_one("tr")
    if not header:
        return {}
    labels = [c.get_text(" ", strip=True).lower() for c in header.select("th, td")]
    columns: dict[str, int] = {}
    for index, label in enumerate(labels):
        normalized = label.replace(" ", "")
        if normalized in {"k-d", "kills-deaths", "kd"}:
            columns.setdefault("kd", index)
        elif label.startswith("adr"):
            columns.setdefault("adr", index)
        elif label.startswith("kast"):
            columns.setdefault("kast", index)
        elif label.startswith("rating"):
            columns.setdefault("rating", index)
        elif label.startswith("hs") or "headshot" in label:
            columns.setdefault("hs", index)
    return columns


def _stat_values_from_cells(cells: list[str], col_map: dict[str, int]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if "kd" in col_map and col_map["kd"] < len(cells):
        kd = re.search(r"(\d+)\s*-\s*(\d+)", cells[col_map["kd"]])
        if kd:
            values["kills"] = int(kd.group(1))
            values["deaths"] = int(kd.group(2))
    for column, field in (("adr", "adr"), ("rating", "rating"), ("kast", "kast_pct"), ("hs", "headshot_pct")):
        index = col_map.get(column)
        if index is not None and index < len(cells):
            number = _first_number(cells[index])
            if number is not None:
                values[field] = number
    return values


def _first_number(text: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(text))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_stats_map_detailed(html: str) -> list[dict[str, Any]]:
    """Parse the detailed /stats/ map page (fetched via the unblocker).

    Returns one row per player with the granular fields HLTV only exposes here:
    opening duels, multi-kills, clutches, headshot kills, flash assists, and
    trade deaths. Rows are matched back to fixtures by nickname (the rendered
    table has no /player/ links)."""
    if BeautifulSoup is None:
        return []
    soup = _soup(html)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for table in soup.select("table.stats-table.totalstats, table.stats-table"):
        if "ctstats" in (table.get("class") or []) or "tstats" in (table.get("class") or []):
            continue
        labels = [c.get_text(" ", strip=True).lower() for c in (table.select("tr")[0].select("th, td") if table.select("tr") else [])]
        col = _detailed_columns(labels)
        if "kills" not in col and "rating" not in col:
            continue
        for tr in table.select("tr")[1:]:
            cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if len(cells) < 3:
                continue
            nickname = cells[0].strip()
            if not nickname or nickname.lower() in seen:
                continue
            seen.add(nickname.lower())
            rows.append(_detailed_row(nickname, cells, col))
    return rows


def _detailed_columns(labels: list[str]) -> dict[str, int]:
    col: dict[str, int] = {}
    for i, label in enumerate(labels):
        norm = label.replace(" ", "")
        if norm.startswith("op.k") and "ek" not in norm:
            col.setdefault("opening", i)
        elif norm == "mks":
            col.setdefault("mks", i)
        elif norm == "1vsx":
            col.setdefault("clutches", i)
        elif norm.startswith("k(hs") or norm == "k(hs)":
            col.setdefault("kills", i)
        elif norm.startswith("a(f"):
            col.setdefault("assists", i)
        elif norm.startswith("d(t"):
            col.setdefault("deaths", i)
        elif label.startswith("adr"):
            col.setdefault("adr", i)
        elif label.startswith("kast"):
            col.setdefault("kast", i)
        elif label.startswith("rating"):
            col.setdefault("rating", i)
    return col


def _detailed_row(nickname: str, cells: list[str], col: dict[str, int]) -> dict[str, Any]:
    row: dict[str, Any] = {"nickname": nickname}

    def cell(key: str) -> str | None:
        i = col.get(key)
        return cells[i] if i is not None and i < len(cells) else None

    opening = cell("opening")
    if opening:
        m = re.search(r"(\d+)\s*:\s*(\d+)", opening)
        if m:
            row["first_kills"], row["first_deaths"] = int(m.group(1)), int(m.group(2))
    # "K (hs)" -> kills (headshot kills); same shape for assists/deaths.
    for key, base, paren in (("kills", "kills", "hs_kills"), ("assists", "assists", "flash_assists"), ("deaths", "deaths", "trade_deaths")):
        text = cell(key)
        if text:
            m = re.search(r"(\d+)\s*(?:\((\d+)\))?", text)
            if m:
                row[base] = int(m.group(1))
                if m.group(2) is not None:
                    row[paren] = int(m.group(2))
    for key, field in (("mks", "multi_kills"), ("clutches", "clutches_won")):
        n = _first_number(cell(key) or "")
        if n is not None:
            row[field] = int(n)
    for key, field in (("adr", "adr"), ("kast", "kast_pct"), ("rating", "rating")):
        n = _first_number(cell(key) or "")
        if n is not None:
            row[field] = n
    if row.get("kills") and row.get("hs_kills") is not None:
        row["headshot_pct"] = round(100.0 * row["hs_kills"] / row["kills"], 1)
    return row


def _parse_half_scores(text: str, total_a: int, total_b: int) -> dict[str, Any]:
    half_pattern = re.compile(r"(\d{1,2})\s*[:;]\s*(\d{1,2})\s*[/|,]\s*(\d{1,2})\s*[:;]\s*(\d{1,2})")
    match = half_pattern.search(text)
    if match:
        h1_a, h1_b = int(match.group(1)), int(match.group(2))
        h2_a, h2_b = int(match.group(3)), int(match.group(4))
        overtime = (total_a + total_b) > (h1_a + h1_b + h2_a + h2_b) or total_a + total_b > 30
        return {
            "team_a_first_half": h1_a,
            "team_b_first_half": h1_b,
            "team_a_second_half": h2_a,
            "team_b_second_half": h2_b,
            "overtime": overtime,
        }
    overtime = total_a + total_b > 30
    return {
        "team_a_first_half": None,
        "team_b_first_half": None,
        "team_a_second_half": None,
        "team_b_second_half": None,
        "overtime": overtime,
    }


def _soup_map_stats_ids(soup) -> list[str]:
    ids = []
    for link in soup.select("a[href*='mapstatsid/']"):
        href = link.get("href") or ""
        match = re.search(r"mapstatsid/(\d+)", href)
        if match:
            ids.append(match.group(1))
    return ids


_VETO_MAP_RE = re.compile(
    r"(Mirage|Inferno|Nuke|Ancient|Anubis|Dust2|Train|Vertigo|Overpass|Cache|Cobblestone)",
    re.I,
)
_VETO_LINE_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")


def _vetoes(soup, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    """Parse the standard HLTV veto box.

    The veto box renders one numbered ``<div>`` per step inside
    ``div.veto-box > div.padding``, e.g. ``1. Entropiq removed Inferno`` and a
    final ``7. Mirage was left over`` decider. We parse those lines directly so
    order_idx, team, and action map to the real sequence. If no numbered box is
    present (e.g. condensed test markup) we fall back to a loose text scan.
    """
    vetoes = _vetoes_from_box(soup, teams)
    return vetoes if vetoes else _vetoes_loose(soup, teams)


def _vetoes_from_box(soup, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    vetoes: list[dict[str, Any]] = []
    for box in soup.select(".veto-box"):
        for line in box.select(".padding > div"):
            text = line.get_text(" ", strip=True)
            line_match = _VETO_LINE_RE.match(text)
            if not line_match:
                continue
            map_match = _VETO_MAP_RE.search(line_match.group(2))
            if not map_match:
                continue
            order_idx = int(line_match.group(1))
            body = line_match.group(2)
            low = body.lower()
            if "left over" in low or "leftover" in low:
                action, team_id = "decider", None
            else:
                action = "pick" if "pick" in low else "ban"
                team_id = _veto_team(body, teams)
            vetoes.append(
                {"order_idx": order_idx, "team_hltv_id": team_id, "action": action, "map_name": _canonical_map(map_match.group(1))}
            )
    return vetoes


def _veto_team(body: str, teams: tuple[dict[str, str], dict[str, str]]) -> str | None:
    low = body.lower()
    for team in teams:
        if low.startswith(team["name"].lower()):
            return team["hltv_id"]
    for team in teams:
        if team["name"].lower() in low:
            return team["hltv_id"]
    return None


def _vetoes_loose(soup, teams: tuple[dict[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    vetoes = []
    for index, item in enumerate(soup.find_all(string=re.compile(r"\b(removed|picked|ban|pick)\b", re.I)), start=1):
        text = str(item)
        map_match = _VETO_MAP_RE.search(text)
        action = "pick" if re.search(r"picked|pick", text, re.I) else "ban"
        if map_match:
            team_id = _veto_team(text, teams)
            vetoes.append({"order_idx": index, "team_hltv_id": team_id, "action": action, "map_name": _canonical_map(map_match.group(1))})
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
    stars = _match_page_stars(soup)
    return {"hltv_id": match.group(1) if match else "unknown", "name": link.get_text(" ", strip=True), "stars": stars}


def _match_page_stars(soup) -> int | None:
    star_attr = soup.select_one("[stars]")
    if star_attr and star_attr.get("stars"):
        try:
            return int(star_attr["stars"])
        except (ValueError, TypeError):
            pass
    filled = soup.select("i.fa-star:not(.faded), .star.filled, .star:not(.empty)")
    if filled:
        return len(filled)
    text = soup.get_text(" ")
    m = re.search(r"(\d)\s*(?:star|/5)", text, re.I)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 5:
            return val
    return None


def _match_stage(soup) -> str | None:
    el = soup.select_one(".match-header-vs-note, .matchInfoEmpty .text")
    if el:
        text = el.get_text(" ", strip=True)
        if text and len(text) < 100:
            return text
    text = soup.get_text(" ", strip=True)
    stage_pattern = re.compile(
        r"(Grand Final|Semi[-\s]?final|Quarter[-\s]?final|"
        r"Group\s*(?:Stage)?(?:\s*[A-D])?|"
        r"Upper\s*(?:Bracket)?|Lower\s*(?:Bracket)?|"
        r"Consolidation|Elimination|"
        r"Round\s*of\s*\d+|"
        r"Playoffs?|Opening\s*Match|"
        r"Decider\s*Match|Winners?\s*Match|"
        r"3rd\s*Place)",
        re.I,
    )
    match = stage_pattern.search(text[:2000])
    return match.group(0).strip() if match else None


def _head_to_head(soup, teams: tuple[dict[str, str], dict[str, str]]) -> dict[str, Any] | None:
    h2h_section = soup.select_one(".head-to-head, .past-matches, [class*=headtohead], [class*=h2h]")
    if not h2h_section:
        text = soup.get_text(" ", strip=True)
        h2h_match = re.search(r"(?:Head\s*to\s*Head|H2H|Past\s*\d+\s*matches).*?(\d+)\s*[-:]\s*(\d+)", text[:3000], re.I)
        if h2h_match:
            return {"team_a_wins": int(h2h_match.group(1)), "team_b_wins": int(h2h_match.group(2))}
        return None
    text = h2h_section.get_text(" ", strip=True)
    score_match = re.search(r"(\d+)\s*[-:]\s*(\d+)", text)
    if score_match:
        return {"team_a_wins": int(score_match.group(1)), "team_b_wins": int(score_match.group(2))}
    return None


def _best_of(soup, maps: list[dict[str, Any]]) -> int:
    return _resolve_best_of(soup.get_text(" ", strip=True), maps)


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
    if not parent:
        return None
    text = parent.get_text(" ", strip=True)
    # A real event name is short and single-line. When the link is not inside a
    # clean result-con (e.g. featured/news blocks), the parent text is a long
    # concatenated blob of sidebar headlines — reject it rather than store junk.
    if not text or len(text) > 80:
        return None
    return text


def _result_event_name(link) -> str | None:
    title = link.get("title")
    if title:
        return str(title).strip()
    # The match link is nested a few levels below the enclosing .result-con,
    # which carries the .event-name node; search the ancestor, not just the
    # immediate parent.
    con = link.find_parent(class_="result-con") or link.find_parent()
    event = con.select_one(".event-name, .eventName, .matchEventName") if con else None
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
    unix = node.get("data-unix") if node else None
    if not unix:
        # HLTV results/upcoming pages store the timestamp (ms) as
        # data-zonedgrouping-entry-unix on the enclosing .result-con, not as a
        # data-unix descendant of the link.
        con = link.find_parent(attrs={"data-zonedgrouping-entry-unix": True})
        unix = con.get("data-zonedgrouping-entry-unix") if con else None
    if not unix:
        return None
    value = float(unix)
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
        "recent_results": _team_page_recent_results(soup),
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
        "per_map_stats": _player_page_map_stats(soup, text),
        "recent_form": _player_page_recent_form(soup),
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


def _team_page_recent_results(soup) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for link in soup.select("a[href*='/matches/']"):
        href = link.get("href") or ""
        match = re.search(r"/matches/(\d+)/", href)
        if not match:
            continue
        text = link.get_text(" ", strip=True)
        score_m = re.search(r"(\d+)\s*[-:]\s*(\d+)", text)
        if not score_m:
            continue
        opponent = ""
        opponent_el = link.select_one(".team-name, .opponent")
        if opponent_el:
            opponent = opponent_el.get_text(strip=True)
        event_el = link.select_one(".event-name, .event")
        event_name = event_el.get_text(strip=True) if event_el else ""
        results.append({
            "match_id": match.group(1),
            "score_won": int(score_m.group(1)),
            "score_lost": int(score_m.group(2)),
            "opponent": opponent,
            "event": event_name,
        })
        if len(results) >= 20:
            break
    return results


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
        "recent_results": [],
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


def _player_page_map_stats(soup, text: str) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    map_names = {"Mirage", "Inferno", "Nuke", "Ancient", "Anubis", "Dust2", "Train", "Vertigo", "Overpass", "Cache"}
    for map_name in map_names:
        pattern = re.compile(rf"{map_name}\s+(\d+)\s+/\s+(\d+)", re.I)
        match = pattern.search(text)
        if match:
            maps_played = int(match.group(2))
            wins = int(match.group(1))
            stats.append({"map_name": map_name, "maps_played": maps_played, "wins": wins, "losses": maps_played - wins})
    rating_pattern = re.compile(r"(\w+)\s+([\d.]+)\s*rating", re.I)
    for match in rating_pattern.finditer(text):
        name = match.group(1)
        if name.capitalize() in map_names:
            for entry in stats:
                if entry["map_name"].lower() == name.lower():
                    try:
                        entry["rating"] = float(match.group(2))
                    except ValueError:
                        pass
    return stats


def _player_page_recent_form(soup) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for link in soup.select("a[href*='/stats/matches/mapstatsid/']"):
        href = link.get("href") or ""
        match = re.search(r"/mapstatsid/(\d+)", href)
        if not match:
            continue
        text = link.get_text(" ", strip=True)
        parent = link.find_parent("tr") or link.find_parent("div")
        context = parent.get_text(" ", strip=True) if parent else text
        rating_m = re.search(r"([\d.]+)\s*$", context.strip())
        kd_m = re.search(r"(\d+)\s*[-/]\s*(\d+)", context)
        results.append({
            "map_stats_id": match.group(1),
            "map_name": _extract_map_name(context),
            "rating": float(rating_m.group(1)) if rating_m and _is_rating(rating_m.group(1)) else None,
            "kills": int(kd_m.group(1)) if kd_m else None,
            "deaths": int(kd_m.group(2)) if kd_m else None,
        })
        if len(results) >= 20:
            break
    return results


def _extract_map_name(text: str) -> str | None:
    for name in ("Mirage", "Inferno", "Nuke", "Ancient", "Anubis", "Dust2", "Train", "Vertigo", "Overpass", "Cache"):
        if name.lower() in text.lower():
            return name
    return None


def _is_rating(value: str) -> bool:
    try:
        f = float(value)
        return 0.0 <= f <= 3.0
    except ValueError:
        return False


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
        "per_map_stats": [],
        "recent_form": [],
    }


def _fallback_player_nickname(html: str) -> str:
    match = re.search(r"<title[^>]*>([^<]+)", html, re.I)
    if match:
        return match.group(1).split("|")[0].strip()
    return "Unknown"
