from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sports.cs.normalization.ids import slugify
from sports.cs.maps import normalize_map_name
from sports.cs.normalization.records import CsParsedEvent, CsParsedMap, CsParsedMatch, CsParsedPlayer, CsParsedTeam, CsParsedVeto

_logger = logging.getLogger(__name__)

KAGGLE_HLTV_RESULTS_CS2_URL = "https://www.kaggle.com/datasets/ilyazored/hltv-match-resultscs2/data"
KAGGLE_HLTV_RESULTS_CS2_SOURCE = "kaggle-hltv-results-cs2"
KAGGLE_COUNTER_STRIKE_COMPETITIVE_DATA_URL = "https://www.kaggle.com/datasets/filipechavesdemacedo/counter-strike-competitive-data"
KAGGLE_COUNTER_STRIKE_COMPETITIVE_DATA_SOURCE = "kaggle-counter-strike-competitive-data"
KAGGLE_CSGO_PRO_MATCHES_URL = "https://www.kaggle.com/datasets/mateusdmachado/csgo-professional-matches"
KAGGLE_CSGO_PRO_MATCHES_SOURCE = "kaggle-csgo-pro-matches"
KAGGLE_CS2_ROLLING_STATS_URL = "https://www.kaggle.com/datasets/griffindesroches/cs2-professional-hltv-match-data-time-series"
KAGGLE_CS2_ROLLING_STATS_SOURCE = "kaggle-cs2-rolling-stats"
KAGGLE_CS2_MATCH_DATA_BETTING_URL = "https://www.kaggle.com/datasets/victorpicinin/counter-strike-2-hltv-match-data"
KAGGLE_CS2_MATCH_DATA_BETTING_SOURCE = "kaggle-cs2-match-data-betting"


def parse_kaggle_hltv_results_csv(path: Path, limit: int | None = None) -> list[CsParsedMatch]:
    """Parse the Kaggle HLTV MATCH RESULTS|CS2 CSV into fixture-compatible matches.

    The dataset has match-level winners and series scores, but not HLTV numeric IDs,
    map names, or per-map winners. We therefore create deterministic synthetic IDs
    and leave `maps` empty rather than inventing map-level facts.
    """

    matches: list[CsParsedMatch] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=2):
            if limit is not None and len(matches) >= limit:
                break
            matches.append(parse_kaggle_hltv_results_row(row, row_index=row_index))
    return matches


def parse_kaggle_hltv_results_row(row: dict[str, Any], row_index: int = 0) -> CsParsedMatch:
    clean = {_clean_key(key): str(value).strip() for key, value in row.items() if key is not None and value is not None}
    required = ("team1", "team2", "event_name", "time", "shape", "score")
    missing = [key for key in required if not clean.get(key)]
    if missing:
        suffix = f" at CSV row {row_index}" if row_index else ""
        raise ValueError(f"missing Kaggle HLTV result columns{suffix}: {', '.join(missing)}")

    team1 = clean["team1"]
    team2 = clean["team2"]
    score_a, score_b = _parse_series_score(clean["score"])
    target = clean.get("target")
    team_won = clean.get("team_won")
    winner_name = _winner_name(team1, team2, score_a, score_b, target, team_won)
    if winner_name not in {team1, team2}:
        suffix = f" at CSV row {row_index}" if row_index else ""
        raise ValueError(f"winner does not match team1/team2{suffix}: {winner_name}")

    source_id = _source_id(clean)
    scheduled_at = _parse_date(clean["time"])
    return CsParsedMatch(
        hltv_id=source_id,
        scheduled_at=scheduled_at,
        best_of=_parse_best_of(clean["shape"], score_a, score_b),
        status="finished",
        team_a=CsParsedTeam(hltv_id=_synthetic_team_id(team1), name=team1),
        team_b=CsParsedTeam(hltv_id=_synthetic_team_id(team2), name=team2),
        event=CsParsedEvent(
            hltv_id=_synthetic_event_id(clean["event_name"]),
            name=clean["event_name"],
            tier=clean.get("stars_of_tournament") or None,
        ),
        players=(),
        maps=(),
        vetoes=(),
    )


def kaggle_hltv_match_to_fixture_payload(match: CsParsedMatch) -> dict[str, Any]:
    return {
        "hltv_id": match.hltv_id,
        "scheduled_at": match.scheduled_at.isoformat(),
        "best_of": match.best_of,
        "status": match.status,
        "team_a": {
            "hltv_id": match.team_a.hltv_id,
            "name": match.team_a.name,
            "aliases": list(match.team_a.aliases),
        },
        "team_b": {
            "hltv_id": match.team_b.hltv_id,
            "name": match.team_b.name,
            "aliases": list(match.team_b.aliases),
        },
        "event": {
            "hltv_id": match.event.hltv_id,
            "name": match.event.name,
            "tier": match.event.tier,
        },
        "players": [
            {
                "hltv_id": player.hltv_id,
                "nickname": player.nickname,
                "team_hltv_id": player.team_hltv_id,
            }
            for player in match.players
        ],
        "maps": [
            {
                "map_index": played_map.map_index,
                "map_name": played_map.map_name,
                "team_a_score": played_map.team_a_score,
                "team_b_score": played_map.team_b_score,
                "winner_hltv_id": played_map.winner_hltv_id,
            }
            for played_map in match.maps
        ],
        "vetoes": [],
        "source": {
            "name": KAGGLE_HLTV_RESULTS_CS2_SOURCE,
            "url": KAGGLE_HLTV_RESULTS_CS2_URL,
            "note": "match-level Kaggle export; no real HLTV IDs or per-map facts available",
        },
    }


def write_kaggle_hltv_fixture_payloads(matches: list[CsParsedMatch], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for match in matches:
        path = out_dir / f"{match.hltv_id}.json"
        path.write_text(json.dumps(kaggle_hltv_match_to_fixture_payload(match), indent=2, sort_keys=True), encoding="utf-8")
        written.append(path)
    return written


def parse_kaggle_competitive_match_results_csv(
    path: Path,
    players_path: Path | None = None,
    limit: int | None = None,
) -> list[CsParsedMatch]:
    """Parse the richer Kaggle Counter Strike Competitive Data match_results.csv.

    This source is map-level and usually carries HLTV match/team IDs, so it can
    produce fixtures with map winners instead of match-only shells.
    """

    grouped: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=2):
            clean = {_clean_key(key): str(value).strip() for key, value in row.items() if key is not None and value is not None}
            clean["_row_index"] = str(row_index)
            match_id = _first(clean, "match_id", "id")
            if not match_id:
                match_id = _competitive_synthetic_match_id(clean)
            if match_id not in grouped:
                grouped[match_id] = []
                order.append(match_id)
            grouped[match_id].append(clean)

    players_by_match = _read_competitive_players(players_path) if players_path is not None else {}
    matches: list[CsParsedMatch] = []
    for match_id in order:
        if limit is not None and len(matches) >= limit:
            break
        matches.append(_parse_competitive_match_group(match_id, grouped[match_id], players_by_match.get(match_id, [])))
    return matches


def kaggle_competitive_match_to_fixture_payload(match: CsParsedMatch) -> dict[str, Any]:
    payload = kaggle_hltv_match_to_fixture_payload(match)
    payload["source"] = {
        "name": KAGGLE_COUNTER_STRIKE_COMPETITIVE_DATA_SOURCE,
        "url": KAGGLE_COUNTER_STRIKE_COMPETITIVE_DATA_URL,
        "note": "map-level Kaggle export with HLTV-derived match/team IDs when present",
    }
    return payload


def write_kaggle_competitive_fixture_payloads(matches: list[CsParsedMatch], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for match in matches:
        path = out_dir / f"{match.hltv_id}.json"
        path.write_text(json.dumps(kaggle_competitive_match_to_fixture_payload(match), indent=2, sort_keys=True), encoding="utf-8")
        written.append(path)
    return written


def _clean_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _parse_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _parse_timestamp(row: dict[str, str]) -> datetime:
    unix_value = _first(row, "unix_data", "data_unix", "date_unix")
    if unix_value:
        numeric = float(unix_value)
        if numeric > 10_000_000_000:
            numeric = numeric / 1000
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    date_value = _first(row, "date", "time")
    if date_value:
        return _parse_date(date_value)
    row_index = row.get("_row_index")
    suffix = f" at CSV row {row_index}" if row_index else ""
    raise ValueError(f"missing match date/unix timestamp{suffix}")


def _parse_best_of(value: str, score_a: int, score_b: int) -> int:
    match = re.search(r"bo\s*(\d+)", value.strip().lower())
    if match:
        return int(match.group(1))
    maps_played = score_a + score_b
    return max(1, maps_played if maps_played % 2 == 1 else maps_played + 1)


def _parse_series_score(value: str) -> tuple[int, int]:
    match = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", value)
    if not match:
        raise ValueError(f"invalid series score: {value}")
    return int(match.group(1)), int(match.group(2))


def _winner_name(team1: str, team2: str, score_a: int, score_b: int, target: str | None, team_won: str | None) -> str:
    if team_won:
        return team_won
    if target in {"1", "true", "True"}:
        return team1
    if target in {"0", "false", "False"}:
        return team2
    return team1 if score_a > score_b else team2


def _synthetic_team_id(name: str) -> str:
    return f"kaggle-team-{slugify(name)}"


def _synthetic_event_id(name: str) -> str:
    return f"kaggle-event-{slugify(name)}"


def _source_id(row: dict[str, str]) -> str:
    raw = "|".join(
        [
            row["time"],
            row["event_name"],
            row["team1"],
            row["team2"],
            row["score"],
            row.get("shape", ""),
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"kaggle-cs2-results-{digest}"


def _parse_competitive_match_group(match_id: str, rows: list[dict[str, str]], player_rows: list[dict[str, str]]) -> CsParsedMatch:
    first = rows[0]
    team_a_id = _required(first, "team_1_id", "team1_id", "team_a_id")
    team_b_id = _required(first, "team_2_id", "team2_id", "team_b_id")
    team_a_name = _required(first, "team_1_name", "team1_name", "team_a_name")
    team_b_name = _required(first, "team_2_name", "team2_name", "team_b_name")
    event_name = _required(first, "event_name")
    scheduled_at = _parse_timestamp(first)
    parsed_maps: list[CsParsedMap] = []
    for index, row in enumerate(rows, start=1):
        try:
            parsed_maps.append(_parse_competitive_map(row, index, team_a_id, team_b_id))
        except ValueError:
            continue
    maps = tuple(parsed_maps)
    players = _parse_competitive_players(player_rows, team_a_id, team_a_name, team_b_id, team_b_name)
    return CsParsedMatch(
        hltv_id=str(match_id),
        scheduled_at=scheduled_at,
        best_of=_best_of_from_maps(len(maps)),
        status="finished",
        team_a=CsParsedTeam(hltv_id=team_a_id, name=team_a_name),
        team_b=CsParsedTeam(hltv_id=team_b_id, name=team_b_name),
        event=CsParsedEvent(
            hltv_id=_competitive_event_id(first),
            name=event_name,
            tier=None,
        ),
        players=players,
        maps=maps,
        vetoes=(),
    )


def _parse_competitive_map(row: dict[str, str], map_index: int, team_a_id: str, team_b_id: str) -> CsParsedMap:
    team_a_score = int(_required(row, "team_1_score", "team1_score", "team_a_score"))
    team_b_score = int(_required(row, "team_2_score", "team2_score", "team_b_score"))
    if team_a_score == team_b_score:
        row_index = row.get("_row_index")
        suffix = f" at CSV row {row_index}" if row_index else ""
        raise ValueError(f"cannot infer map winner from tied score{suffix}: {team_a_score}-{team_b_score}")
    return CsParsedMap(
        map_index=map_index,
        map_name=normalize_map_name(_required(row, "map", "map_name")),
        team_a_score=team_a_score,
        team_b_score=team_b_score,
        winner_hltv_id=team_a_id if team_a_score > team_b_score else team_b_id,
    )


def _first(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return None


def _required(row: dict[str, str], *keys: str) -> str:
    value = _first(row, *keys)
    if value is not None:
        return value
    row_index = row.get("_row_index")
    suffix = f" at CSV row {row_index}" if row_index else ""
    raise ValueError(f"missing Kaggle competitive column{suffix}: {'/'.join(keys)}")


def _best_of_from_maps(maps_played: int) -> int:
    if maps_played <= 1:
        return 1
    return maps_played if maps_played % 2 == 1 else maps_played + 1


def _competitive_event_id(row: dict[str, str]) -> str:
    event_link = _first(row, "event_link", "event_url")
    if event_link:
        digits = re.findall(r"\d+", event_link)
        if digits:
            return digits[-1]
    return f"kaggle-event-{slugify(_required(row, 'event_name'))}"


def _competitive_synthetic_match_id(row: dict[str, str]) -> str:
    raw = "|".join(
        [
            _first(row, "unix_data", "data_unix", "date", "time") or "",
            _first(row, "event_name") or "",
            _first(row, "team_1_name", "team1_name", "team_a_name") or "",
            _first(row, "team_2_name", "team2_name", "team_b_name") or "",
            _first(row, "match_link", "match_url") or "",
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"kaggle-competitive-{digest}"


def _read_competitive_players(path: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=2):
            clean = {_clean_key(key): str(value).strip() for key, value in row.items() if key is not None and value is not None}
            clean["_row_index"] = str(row_index)
            match_id = _first(clean, "match_id")
            if not match_id:
                match_id = _player_match_id_from_link(clean)
            if match_id:
                grouped.setdefault(match_id, []).append(clean)
    return grouped


def _parse_competitive_players(
    rows: list[dict[str, str]],
    team_a_id: str,
    team_a_name: str,
    team_b_id: str,
    team_b_name: str,
) -> tuple[CsParsedPlayer, ...]:
    players: list[CsParsedPlayer] = []
    seen: set[str] = set()
    for row in rows:
        player_id = _first(row, "player_id")
        if not player_id:
            player_id = _player_id_from_link(row)
        nickname = _first(row, "player_nick", "nickname", "player_name", "name")
        team_name = _first(row, "team_name")
        if not player_id or not nickname or not team_name:
            continue
        team_id = _team_id_from_name(team_name, team_a_id, team_a_name, team_b_id, team_b_name)
        if team_id is None or player_id in seen:
            continue
        seen.add(player_id)
        players.append(CsParsedPlayer(hltv_id=player_id, nickname=nickname, team_hltv_id=team_id))
    return tuple(players)


def _player_match_id_from_link(row: dict[str, str]) -> str | None:
    link = _first(row, "match_link", "match_url")
    if not link:
        return None
    match = re.search(r"/matches/(\d+)", link)
    return match.group(1) if match else None


def _player_id_from_link(row: dict[str, str]) -> str | None:
    link = _first(row, "players_link", "player_link", "player_url")
    if not link:
        return None
    match = re.search(r"/player/(\d+)", link)
    return match.group(1) if match else None


def _team_id_from_name(team_name: str, team_a_id: str, team_a_name: str, team_b_id: str, team_b_name: str) -> str | None:
    normalized = slugify(team_name)
    if normalized == slugify(team_a_name):
        return team_a_id
    if normalized == slugify(team_b_name):
        return team_b_id
    return None


# ---------------------------------------------------------------------------
# Kaggle CS:GO Professional Matches (mateusdmachado) converter
# Dataset: results.csv, picks.csv, economy.csv, players.csv
# ~25K matches from Nov 2015 to Mar 2020
# ---------------------------------------------------------------------------


def parse_kaggle_csgo_pro_results_csv(
    path: Path,
    picks_path: Path | None = None,
    players_path: Path | None = None,
    limit: int | None = None,
) -> list[CsParsedMatch]:
    """Parse the Kaggle CS:GO Professional Matches *results.csv* into fixtures.

    This dataset is map-level: each CSV row is one map inside a series.  Rows
    sharing the same ``match_id`` are grouped into one :class:`CsParsedMatch`.
    The optional *picks_path* and *players_path* arguments allow joining veto
    sequences and per-player stats respectively.
    """

    grouped: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    skipped_maps = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=2):
            clean = {_clean_key(key): str(value).strip() for key, value in row.items() if key is not None and value is not None}
            clean["_row_index"] = str(row_index)

            # Validate that map name is recognised; skip row if not
            raw_map = _first(clean, "map", "map_name", "_map")
            if raw_map:
                try:
                    normalize_map_name(raw_map)
                except ValueError:
                    skipped_maps += 1
                    _logger.warning("skipping row %s with unknown map: %s", row_index, raw_map)
                    continue

            match_id = _first(clean, "match_id", "id")
            if not match_id:
                match_id = _csgo_pro_synthetic_match_id(clean)
            if match_id not in grouped:
                grouped[match_id] = []
                order.append(match_id)
            grouped[match_id].append(clean)

    if skipped_maps:
        _logger.info("skipped %d rows with unknown map names", skipped_maps)

    picks_by_match = _read_csgo_pro_picks(picks_path) if picks_path is not None else {}
    players_by_match = _read_csgo_pro_players(players_path) if players_path is not None else {}

    matches: list[CsParsedMatch] = []
    for match_id in order:
        if limit is not None and len(matches) >= limit:
            break
        matches.append(
            _parse_csgo_pro_match_group(
                match_id,
                grouped[match_id],
                picks_by_match.get(match_id, []),
                players_by_match.get(match_id, []),
            )
        )
    return matches


def kaggle_csgo_pro_match_to_fixture_payload(match: CsParsedMatch) -> dict[str, Any]:
    """Serialise a :class:`CsParsedMatch` from the CS:GO Pro dataset to a JSON-ready dict."""
    payload = kaggle_hltv_match_to_fixture_payload(match)
    payload["vetoes"] = [
        {
            "order_idx": veto.order_idx,
            "team_hltv_id": veto.team_hltv_id,
            "action": veto.action,
            "map_name": veto.map_name,
        }
        for veto in match.vetoes
    ]
    payload["source"] = {
        "name": KAGGLE_CSGO_PRO_MATCHES_SOURCE,
        "url": KAGGLE_CSGO_PRO_MATCHES_URL,
        "note": "map-level Kaggle CS:GO Professional Matches export with veto and player data when available",
    }
    return payload


def write_kaggle_csgo_pro_fixture_payloads(matches: list[CsParsedMatch], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for match in matches:
        filepath = out_dir / f"{match.hltv_id}.json"
        filepath.write_text(
            json.dumps(kaggle_csgo_pro_match_to_fixture_payload(match), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        written.append(filepath)
    return written


# -- internal helpers for CS:GO Pro Matches dataset -------------------------


def _parse_csgo_pro_match_group(
    match_id: str,
    rows: list[dict[str, str]],
    pick_rows: list[dict[str, str]],
    player_rows: list[dict[str, str]],
) -> CsParsedMatch:
    first = rows[0]

    team_a_name = _required(first, "team_1", "team1", "team_a", "team_1_name", "team1_name")
    team_b_name = _required(first, "team_2", "team2", "team_b", "team_2_name", "team2_name")
    team_a_id = _first(first, "team_1_id", "team1_id") or _synthetic_team_id(team_a_name)
    team_b_id = _first(first, "team_2_id", "team2_id") or _synthetic_team_id(team_b_name)

    event_name = _first(first, "event_name", "event", "tournament") or "Unknown Event"
    event_id = _first(first, "event_id") or _synthetic_event_id(event_name)

    scheduled_at = _parse_csgo_pro_date(first)

    best_of_raw = _first(first, "best_of", "best_of_maps", "bo")
    best_of = int(best_of_raw) if best_of_raw and best_of_raw.isdigit() else _best_of_from_maps(len(rows))

    # Ranking info (informational, not stored in CsParsedMatch but could be useful in payload)
    maps = tuple(_parse_csgo_pro_map(row, index, team_a_id, team_b_id) for index, row in enumerate(rows, start=1))
    vetoes = _parse_csgo_pro_vetoes(pick_rows, team_a_name, team_b_name, team_a_id, team_b_id)
    players = _parse_csgo_pro_players(player_rows, team_a_id, team_a_name, team_b_id, team_b_name)

    return CsParsedMatch(
        hltv_id=str(match_id),
        scheduled_at=scheduled_at,
        best_of=best_of,
        status="finished",
        team_a=CsParsedTeam(hltv_id=team_a_id, name=team_a_name),
        team_b=CsParsedTeam(hltv_id=team_b_id, name=team_b_name),
        event=CsParsedEvent(hltv_id=event_id, name=event_name, tier=None),
        players=players,
        maps=maps,
        vetoes=vetoes,
    )


def _parse_csgo_pro_map(row: dict[str, str], map_index: int, team_a_id: str, team_b_id: str) -> CsParsedMap:
    raw_map = _first(row, "map", "map_name", "_map")
    map_name = normalize_map_name(raw_map) if raw_map else "Unknown"

    # Parse round scores - could be "16-8", "16 - 8", or separate columns
    score_str = _first(row, "result", "score", "map_score", "result_score")
    team_a_score: int | None = None
    team_b_score: int | None = None

    if score_str:
        score_match = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", score_str)
        if score_match:
            team_a_score = int(score_match.group(1))
            team_b_score = int(score_match.group(2))

    if team_a_score is None:
        raw_a = _first(row, "result_1", "team_1_score", "team1_score", "team_a_score", "t1_score")
        raw_b = _first(row, "result_2", "team_2_score", "team2_score", "team_b_score", "t2_score")
        if raw_a is not None and raw_b is not None:
            team_a_score = int(raw_a)
            team_b_score = int(raw_b)

    if team_a_score is None or team_b_score is None:
        row_index = row.get("_row_index")
        suffix = f" at CSV row {row_index}" if row_index else ""
        raise ValueError(f"cannot parse map scores{suffix}")

    if team_a_score == team_b_score:
        winner_col = _first(row, "map_winner", "winner")
        if winner_col in ("1", "team_1"):
            winner_id = team_a_id
        elif winner_col in ("2", "team_2"):
            winner_id = team_b_id
        elif winner_col and slugify(winner_col) == slugify(row.get("team_1", "") or row.get("team1", "") or ""):
            winner_id = team_a_id
        elif winner_col:
            winner_id = team_b_id
        else:
            row_index = row.get("_row_index")
            suffix = f" at CSV row {row_index}" if row_index else ""
            raise ValueError(f"cannot infer map winner from tied score{suffix}: {team_a_score}-{team_b_score}")
    else:
        winner_id = team_a_id if team_a_score > team_b_score else team_b_id

    return CsParsedMap(
        map_index=map_index,
        map_name=map_name,
        team_a_score=team_a_score,
        team_b_score=team_b_score,
        winner_hltv_id=winner_id,
    )


def _parse_csgo_pro_date(row: dict[str, str]) -> datetime:
    """Extract a date from various column names in the CS:GO Pro dataset."""
    date_str = _first(row, "date", "time", "match_date")
    if date_str:
        return _parse_date(date_str)
    unix_str = _first(row, "date_unix", "unix_data", "data_unix", "unix_timestamp")
    if unix_str:
        numeric = float(unix_str)
        if numeric > 10_000_000_000:
            numeric = numeric / 1000
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    row_index = row.get("_row_index")
    suffix = f" at CSV row {row_index}" if row_index else ""
    raise ValueError(f"missing date column in CS:GO Pro results{suffix}")


def _csgo_pro_synthetic_match_id(row: dict[str, str]) -> str:
    raw = "|".join([
        _first(row, "date", "time", "match_date") or "",
        _first(row, "event_name", "event", "tournament") or "",
        _first(row, "team_1", "team1", "team_a") or "",
        _first(row, "team_2", "team2", "team_b") or "",
        _first(row, "map", "map_name") or "",
    ])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"kaggle-csgo-pro-{digest}"


def _read_csgo_pro_picks(path: Path) -> dict[str, list[dict[str, str]]]:
    """Read picks.csv and group rows by match_id."""
    grouped: dict[str, list[dict[str, str]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=2):
            clean = {_clean_key(key): str(value).strip() for key, value in row.items() if key is not None and value is not None}
            clean["_row_index"] = str(row_index)
            match_id = _first(clean, "match_id", "id")
            if match_id:
                grouped.setdefault(match_id, []).append(clean)
    return grouped


def _parse_csgo_pro_vetoes(
    rows: list[dict[str, str]],
    team_a_name: str,
    team_b_name: str,
    team_a_id: str,
    team_b_id: str,
) -> tuple[CsParsedVeto, ...]:
    """Convert pick/ban rows into CsParsedVeto tuples.

    Supports two formats:
    1. Wide format (one row per match): columns like ``t1_removed_1``,
       ``t2_removed_1``, ``t1_picked_1``, ``t2_picked_1``, ``left_over``.
    2. Narrow format (one row per veto): columns like ``map``, ``action``,
       ``team``.
    """
    if not rows:
        return ()

    first = rows[0]
    if any(k.startswith("t1_removed") or k.startswith("t2_removed") for k in first):
        return _parse_csgo_pro_vetoes_wide(first, team_a_name, team_b_name, team_a_id, team_b_id)

    vetoes: list[CsParsedVeto] = []
    for idx, row in enumerate(rows, start=1):
        raw_map = _first(row, "map", "map_name", "pick_map", "_map")
        if not raw_map:
            continue
        try:
            map_name = normalize_map_name(raw_map)
        except ValueError:
            _logger.warning("skipping veto with unknown map: %s", raw_map)
            continue

        action = _first(row, "pick_type", "type", "action", "veto_type") or "unknown"
        action = action.strip().lower()

        team_name = _first(row, "team", "team_name", "pick_team")
        team_id: str | None = None
        if team_name:
            team_id = _team_id_from_name(team_name, team_a_id, team_a_name, team_b_id, team_b_name)
        if team_id is None:
            team_num = _first(row, "team_number", "team_num", "pick_team_number")
            if team_num == "1":
                team_id = team_a_id
            elif team_num == "2":
                team_id = team_b_id

        vetoes.append(CsParsedVeto(
            order_idx=idx,
            team_hltv_id=team_id,
            action=action,
            map_name=map_name,
        ))
    return tuple(vetoes)


def _parse_csgo_pro_vetoes_wide(
    row: dict[str, str],
    team_a_name: str,
    team_b_name: str,
    team_a_id: str,
    team_b_id: str,
) -> tuple[CsParsedVeto, ...]:
    """Parse the wide picks format: t1_removed_1..3, t2_removed_1..3, t1_picked_1, t2_picked_1, left_over."""
    inverted = row.get("inverted_teams", "0") in ("1", "true", "True")
    pick_team_1 = _first(row, "team_1", "team1") or ""
    if inverted or (pick_team_1 and slugify(pick_team_1) == slugify(team_b_name)):
        t1_id, t2_id = team_b_id, team_a_id
    else:
        t1_id, t2_id = team_a_id, team_b_id

    vetoes: list[CsParsedVeto] = []
    idx = 0

    veto_sequence: list[tuple[str, str, str]] = []
    for i in range(1, 4):
        val = row.get(f"t1_removed_{i}", "")
        if val and val not in ("0", "0.0", ""):
            veto_sequence.append((t1_id, "ban", val))
    for i in range(1, 4):
        val = row.get(f"t2_removed_{i}", "")
        if val and val not in ("0", "0.0", ""):
            veto_sequence.append((t2_id, "ban", val))

    for i in range(1, 4):
        val = row.get(f"t1_picked_{i}", "")
        if val and val not in ("0", "0.0", ""):
            veto_sequence.append((t1_id, "pick", val))
    for i in range(1, 4):
        val = row.get(f"t2_picked_{i}", "")
        if val and val not in ("0", "0.0", ""):
            veto_sequence.append((t2_id, "pick", val))

    left_over = row.get("left_over", "")
    if left_over and left_over not in ("0", "0.0", ""):
        veto_sequence.append((None, "left_over", left_over))

    for team_id_val, action, raw_map in veto_sequence:
        try:
            map_name = normalize_map_name(raw_map)
        except ValueError:
            _logger.warning("skipping veto with unknown map: %s", raw_map)
            continue
        idx += 1
        vetoes.append(CsParsedVeto(
            order_idx=idx,
            team_hltv_id=team_id_val,
            action=action,
            map_name=map_name,
        ))
    return tuple(vetoes)


def _read_csgo_pro_players(path: Path) -> dict[str, list[dict[str, str]]]:
    """Read players.csv and group rows by match_id."""
    grouped: dict[str, list[dict[str, str]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=2):
            clean = {_clean_key(key): str(value).strip() for key, value in row.items() if key is not None and value is not None}
            clean["_row_index"] = str(row_index)
            match_id = _first(clean, "match_id", "id")
            if match_id:
                grouped.setdefault(match_id, []).append(clean)
    return grouped


def _parse_csgo_pro_players(
    rows: list[dict[str, str]],
    team_a_id: str,
    team_a_name: str,
    team_b_id: str,
    team_b_name: str,
) -> tuple[CsParsedPlayer, ...]:
    """Convert player CSV rows into CsParsedPlayer tuples (deduplicated)."""
    players: list[CsParsedPlayer] = []
    seen: set[str] = set()
    for row in rows:
        player_id = _first(row, "player_id", "id")
        nickname = _first(row, "player_name", "nickname", "player_nick", "name")
        team_name = _first(row, "team", "team_name", "player_team")
        if not nickname:
            continue
        if not player_id:
            player_id = f"kaggle-player-{slugify(nickname)}"
        team_id: str | None = None
        if team_name:
            team_id = _team_id_from_name(team_name, team_a_id, team_a_name, team_b_id, team_b_name)
        if team_id is None:
            continue
        if player_id in seen:
            continue
        seen.add(player_id)
        players.append(CsParsedPlayer(hltv_id=player_id, nickname=nickname, team_hltv_id=team_id))
    return tuple(players)


# ---------------------------------------------------------------------------
# Kaggle CS2 Rolling Stats (Time Series) converter
# Dataset: updated_ts_cs_data.csv (griffindesroches)
# ~8K match-level rows with pre-computed rolling 5-match team features
# ---------------------------------------------------------------------------

_ROLLING_STATS_MATCH_COLS = (
    "opening_kills", "opening_deaths", "multi_kill_rounds", "kast_pct",
    "clutches_won", "kills", "assists", "deaths", "adr", "swing_pct", "rating_3",
)

_ROLLING_STATS_ROLL5_COLS = (
    "roll5_adr", "roll5_assists", "roll5_clutches_won", "roll5_deaths",
    "roll5_kast_pct", "roll5_kills", "roll5_multi_kill_rounds",
    "roll5_opening_deaths", "roll5_opening_kills", "roll5_rating_3",
    "roll5_swing_pct",
)


def parse_kaggle_rolling_stats_csv(
    path: Path,
    limit: int | None = None,
) -> tuple[list[CsParsedMatch], dict[str, dict[str, Any]]]:
    """Parse the CS2 Rolling Stats (Time Series) CSV.

    Returns a tuple of (matches, rolling_features) where rolling_features is
    keyed by match hltv_id and contains per-team match stats and rolling
    5-match averages as point-in-time features.
    """
    matches: list[CsParsedMatch] = []
    features: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=2):
            if limit is not None and len(matches) >= limit:
                break
            clean = {_clean_key(key): str(value).strip() for key, value in row.items() if key is not None and value is not None}
            clean["_row_index"] = str(row_index)
            try:
                match, row_features = _parse_rolling_stats_row(clean)
            except ValueError as exc:
                _logger.warning("skipping rolling stats row %d: %s", row_index, exc)
                continue
            matches.append(match)
            features[match.hltv_id] = row_features
    return matches, features


def kaggle_rolling_stats_match_to_fixture_payload(
    match: CsParsedMatch,
    rolling_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = kaggle_hltv_match_to_fixture_payload(match)
    payload["source"] = {
        "name": KAGGLE_CS2_ROLLING_STATS_SOURCE,
        "url": KAGGLE_CS2_ROLLING_STATS_URL,
        "note": "series-level CS2 rolling stats; no per-map data; rolling features are point-in-time",
    }
    if rolling_features:
        payload["rolling_features"] = rolling_features
    return payload


def write_kaggle_rolling_stats_fixture_payloads(
    matches: list[CsParsedMatch],
    features: dict[str, dict[str, Any]],
    out_dir: Path,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for match in matches:
        filepath = out_dir / f"{match.hltv_id}.json"
        payload = kaggle_rolling_stats_match_to_fixture_payload(match, features.get(match.hltv_id))
        filepath.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        written.append(filepath)
    return written


def _parse_rolling_stats_row(row: dict[str, str]) -> tuple[CsParsedMatch, dict[str, Any]]:
    date_str = _required(row, "date", "time")
    scheduled_at = _parse_date(date_str)

    team1_name = _required(row, "team1_name", "team1")
    team2_name = _required(row, "team2_name", "team2")

    stats_url = _first(row, "detailed_stats_url", "stats_url")
    hltv_stats_id = _extract_hltv_stats_id(stats_url) if stats_url else None
    if hltv_stats_id:
        match_id = f"hltv-stats-{hltv_stats_id}"
    else:
        raw = f"{date_str}|{team1_name}|{team2_name}"
        match_id = f"kaggle-rolling-{hashlib.sha1(raw.encode()).hexdigest()[:12]}"

    score_a = int(_required(row, "team1_score"))
    score_b = int(_required(row, "team2_score"))
    winner_side = _first(row, "winner_side", "winner")
    if winner_side == "team1":
        winner_name = team1_name
    elif winner_side == "team2":
        winner_name = team2_name
    else:
        winner_name = team1_name if score_a > score_b else team2_name

    best_of = max(1, score_a + score_b) if (score_a + score_b) % 2 == 1 else max(1, score_a + score_b + 1)
    event_name = _first(row, "event_name", "event") or "Unknown Event"

    match = CsParsedMatch(
        hltv_id=match_id,
        scheduled_at=scheduled_at,
        best_of=best_of,
        status="finished",
        team_a=CsParsedTeam(hltv_id=_synthetic_team_id(team1_name), name=team1_name),
        team_b=CsParsedTeam(hltv_id=_synthetic_team_id(team2_name), name=team2_name),
        event=CsParsedEvent(hltv_id=_synthetic_event_id(event_name), name=event_name, tier=None),
        players=(),
        maps=(),
        vetoes=(),
    )

    row_features: dict[str, Any] = {}
    if hltv_stats_id:
        row_features["hltv_stats_id"] = hltv_stats_id
    if stats_url:
        row_features["detailed_stats_url"] = stats_url

    for prefix, label in (("team1", "team_a"), ("team2", "team_b")):
        match_stats: dict[str, float | None] = {}
        for col in _ROLLING_STATS_MATCH_COLS:
            val = _first(row, f"{prefix}_{col}")
            match_stats[col] = _safe_float(val)
        row_features[f"{label}_match_stats"] = match_stats

        rolling: dict[str, float | None] = {}
        for col in _ROLLING_STATS_ROLL5_COLS:
            val = _first(row, f"{prefix}_{col}")
            rolling[col] = _safe_float(val)
        row_features[f"{label}_rolling_5"] = rolling

    return match, row_features


def _extract_hltv_stats_id(url: str) -> str | None:
    match = re.search(r"/stats/matches/(\d+)/", url)
    return match.group(1) if match else None


def _safe_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Kaggle CS2 HLTV Match Data for Betting (victorpicinin) converter
# Dataset: CS2_HLTV_MATCH_DATA2.csv (semicolon-delimited)
# ~1.2K map-level rows across ~647 unique matches, per-player stats
# Limitation: no date column — fixtures use epoch sentinel
# ---------------------------------------------------------------------------

_BETTING_PLAYER_STAT_COLS = (
    "total_kills", "headshot_%", "total_deaths", "k/d_ratio",
    "damage_/_round", "grenade_dmg_/_round", "maps_played",
    "rounds_played", "kills_/_round", "assists_/_round",
    "deaths_/_round", "saved_by_teammate_/_round",
    "saved_teammates_/_round", "rating_1.0", "rating_2.0",
)

_EPOCH_SENTINEL = datetime(2000, 1, 1, tzinfo=timezone.utc)


def parse_kaggle_cs2_match_data_csv(
    path: Path,
    limit: int | None = None,
) -> tuple[list[CsParsedMatch], dict[str, dict[str, Any]]]:
    """Parse the semicolon-delimited CS2 HLTV Match Data for Betting CSV.

    Returns (matches, player_features) where player_features is keyed by match
    hltv_id and contains per-player statistics for each team.

    **Limitation**: the dataset has no date column, so all fixtures use an
    epoch sentinel (2000-01-01) for ``scheduled_at``.  These should only
    be used for matchID cross-reference and player stat analysis, not for
    temporal feature construction.
    """
    grouped: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row_index, row in enumerate(reader, start=2):
            clean = {_clean_key(key): str(value).strip() for key, value in row.items() if key is not None and value is not None}
            clean["_row_index"] = str(row_index)
            match_id = _first(clean, "matchid", "match_id", "id")
            if not match_id:
                _logger.warning("skipping row %d with no matchID", row_index)
                continue
            if match_id not in grouped:
                grouped[match_id] = []
                order.append(match_id)
            grouped[match_id].append(clean)

    matches: list[CsParsedMatch] = []
    player_features: dict[str, dict[str, Any]] = {}
    for match_id in order:
        if limit is not None and len(matches) >= limit:
            break
        try:
            match, features = _parse_betting_match_group(match_id, grouped[match_id])
        except ValueError as exc:
            _logger.warning("skipping match %s: %s", match_id, exc)
            continue
        matches.append(match)
        player_features[match.hltv_id] = features
    return matches, player_features


def kaggle_cs2_match_data_to_fixture_payload(
    match: CsParsedMatch,
    player_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = kaggle_hltv_match_to_fixture_payload(match)
    payload["source"] = {
        "name": KAGGLE_CS2_MATCH_DATA_BETTING_SOURCE,
        "url": KAGGLE_CS2_MATCH_DATA_BETTING_URL,
        "note": "map-level CS2 data with per-player stats; no dates available; epoch sentinel used for scheduled_at",
    }
    if player_features:
        payload["player_features"] = player_features
    return payload


def write_kaggle_cs2_match_data_fixture_payloads(
    matches: list[CsParsedMatch],
    player_features: dict[str, dict[str, Any]],
    out_dir: Path,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for match in matches:
        filepath = out_dir / f"{match.hltv_id}.json"
        payload = kaggle_cs2_match_data_to_fixture_payload(match, player_features.get(match.hltv_id))
        filepath.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        written.append(filepath)
    return written


def _parse_betting_match_group(
    match_id: str,
    rows: list[dict[str, str]],
) -> tuple[CsParsedMatch, dict[str, Any]]:
    first = rows[0]
    team_a_name = _required(first, "team1", "team_1", "team1_name")
    team_b_name = _required(first, "team2", "team_2", "team2_name")
    team_a_id = _synthetic_team_id(team_a_name)
    team_b_id = _synthetic_team_id(team_b_name)

    parsed_maps: list[CsParsedMap] = []
    per_map_features: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        raw_map = _first(row, "map", "map_name")
        try:
            map_name = normalize_map_name(raw_map) if raw_map else "Unknown"
        except ValueError:
            _logger.warning("skipping map with unknown name: %s", raw_map)
            continue

        team1_win = _first(row, "team1_win", "team_1_win")
        if team1_win == "1":
            winner_id = team_a_id
        elif team1_win == "0":
            winner_id = team_b_id
        else:
            _logger.warning("skipping map %d of match %s: unclear winner", index, match_id)
            continue

        parsed_maps.append(CsParsedMap(
            map_index=index,
            map_name=map_name,
            team_a_score=0,
            team_b_score=0,
            winner_hltv_id=winner_id,
        ))

        map_features = _extract_betting_player_stats(row, map_name)
        map_features["t1_mapwinrate"] = _safe_pct(row.get("t1_mapwinrate"))
        map_features["t2_mapwinrate"] = _safe_pct(row.get("t2_mapwinrate"))
        per_map_features.append(map_features)

    if not parsed_maps:
        raise ValueError("no valid maps found")

    team_a_wins = sum(1 for m in parsed_maps if m.winner_hltv_id == team_a_id)
    team_b_wins = sum(1 for m in parsed_maps if m.winner_hltv_id == team_b_id)

    match = CsParsedMatch(
        hltv_id=str(match_id),
        scheduled_at=_EPOCH_SENTINEL,
        best_of=_best_of_from_maps(len(parsed_maps)),
        status="finished",
        team_a=CsParsedTeam(hltv_id=team_a_id, name=team_a_name),
        team_b=CsParsedTeam(hltv_id=team_b_id, name=team_b_name),
        event=CsParsedEvent(hltv_id="unknown", name="Unknown Event", tier=None),
        players=(),
        maps=tuple(parsed_maps),
        vetoes=(),
    )

    features: dict[str, Any] = {
        "team_a_map_wins": team_a_wins,
        "team_b_map_wins": team_b_wins,
        "maps": per_map_features,
    }
    return match, features


def _extract_betting_player_stats(row: dict[str, str], map_name: str) -> dict[str, Any]:
    result: dict[str, Any] = {"map_name": map_name}
    for team_prefix, team_label in (("t1", "team_a"), ("t2", "team_b")):
        players: list[dict[str, float | None]] = []
        for i in range(5):
            stats: dict[str, float | None] = {}
            for col in _BETTING_PLAYER_STAT_COLS:
                key = f"{team_prefix}_player{i}_{col}"
                stats[col.replace(" ", "_").replace("/", "_")] = _safe_float(row.get(key))
            if any(v is not None for v in stats.values()):
                players.append(stats)
        result[f"{team_label}_players"] = players
    return result


def _safe_pct(value: str | None) -> float | None:
    if not value or value.strip() == "":
        return None
    cleaned = value.strip().rstrip("%").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None
