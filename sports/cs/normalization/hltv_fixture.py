from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.entities import Competition, Contest, ContestUnit, Participant, ParticipantKind
from sports.cs import GAME_ID
from sports.cs.maps import normalize_map_name
from sports.cs.normalization.ids import cs_contest_id, cs_participant_id
from sports.cs.normalization.records import (
    CsParsedEvent,
    CsParsedMap,
    CsParsedMatch,
    CsParsedPlayer,
    CsParsedPlayerMapStats,
    CsParsedTeam,
    CsParsedVeto,
)


def parse_hltv_fixture(path: Path) -> CsParsedMatch:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_hltv_payload(payload)


def parse_hltv_payload(payload: dict[str, Any]) -> CsParsedMatch:
    team_a = _parse_team(payload["team_a"])
    team_b = _parse_team(payload["team_b"])
    event = payload["event"]
    scheduled_at = _parse_datetime(payload["scheduled_at"])
    players = tuple(_parse_player(row) for row in payload.get("players", []))
    maps = tuple(_parse_map(row, players) for row in payload.get("maps", []))
    vetoes = tuple(_parse_veto(row) for row in payload.get("vetoes", []))
    return CsParsedMatch(
        hltv_id=str(payload["hltv_id"]),
        scheduled_at=scheduled_at,
        best_of=int(payload["best_of"]),
        status=str(payload.get("status", "scheduled")),
        team_a=team_a,
        team_b=team_b,
        event=CsParsedEvent(
            hltv_id=str(event["hltv_id"]),
            name=str(event["name"]),
            tier=_optional_str(event.get("tier")),
        ),
        players=players,
        maps=maps,
        vetoes=vetoes,
        match_stage=_optional_str(payload.get("match_stage")),
        head_to_head=_parse_head_to_head(payload.get("head_to_head")),
    )


def normalize_match(parsed: CsParsedMatch) -> dict[str, object]:
    team_a_id = cs_participant_id("hltv", parsed.team_a.hltv_id)
    team_b_id = cs_participant_id("hltv", parsed.team_b.hltv_id)
    competition_id = f"cs:competition:hltv:{parsed.event.hltv_id}"
    contest_id = cs_contest_id("hltv", parsed.hltv_id)

    participants = [
        Participant(team_a_id, GAME_ID, ParticipantKind.TEAM, parsed.team_a.name, "hltv", parsed.team_a.hltv_id),
        Participant(team_b_id, GAME_ID, ParticipantKind.TEAM, parsed.team_b.name, "hltv", parsed.team_b.hltv_id),
    ]
    participants.extend(
        Participant(
            cs_participant_id("hltv", player.hltv_id),
            GAME_ID,
            ParticipantKind.PLAYER,
            player.nickname,
            "hltv",
            player.hltv_id,
        )
        for player in parsed.players
    )
    contest_units = tuple(
        ContestUnit(
            unit_id=f"{contest_id}:map:{item.map_index}",
            contest_id=contest_id,
            sequence_number=item.map_index,
            unit_type="map",
            name=item.map_name,
            winner_id=cs_participant_id("hltv", item.winner_hltv_id),
        )
        for item in parsed.maps
    )
    return {
        "participants": tuple(participants),
        "competition": Competition(
            competition_id=competition_id,
            game_id=GAME_ID,
            name=parsed.event.name,
            tier=parsed.event.tier,
        ),
        "contest": Contest(
            contest_id=contest_id,
            game_id=GAME_ID,
            competition_id=competition_id,
            starts_at=parsed.scheduled_at,
            participant_a_id=team_a_id,
            participant_b_id=team_b_id,
            format=f"bo{parsed.best_of}",
            status=parsed.status,
            match_stage=parsed.match_stage,
            head_to_head=parsed.head_to_head,
        ),
        "contest_units": contest_units,
        "cs_maps": parsed.maps,
        "cs_vetoes": parsed.vetoes,
    }


def _parse_team(payload: dict[str, Any]) -> CsParsedTeam:
    return CsParsedTeam(
        hltv_id=str(payload["hltv_id"]),
        name=str(payload["name"]),
        aliases=tuple(str(item) for item in payload.get("aliases", [])),
    )


def _parse_player(payload: dict[str, Any]) -> CsParsedPlayer:
    return CsParsedPlayer(
        hltv_id=str(payload["hltv_id"]),
        nickname=str(payload["nickname"]),
        team_hltv_id=str(payload["team_hltv_id"]),
    )


def _parse_map(payload: dict[str, Any], players: tuple[CsParsedPlayer, ...]) -> CsParsedMap:
    raw_stats = payload.get("player_stats") or {}
    return CsParsedMap(
        map_index=int(payload["map_index"]),
        map_name=normalize_map_name(str(payload["map_name"])),
        team_a_score=int(payload["team_a_score"]),
        team_b_score=int(payload["team_b_score"]),
        winner_hltv_id=str(payload["winner_hltv_id"]),
        map_stats_id=_optional_str(payload.get("map_stats_id")),
        overtime=_optional_bool(payload.get("overtime")),
        team_a_first_half=_optional_int(payload.get("team_a_first_half")),
        team_a_second_half=_optional_int(payload.get("team_a_second_half")),
        team_b_first_half=_optional_int(payload.get("team_b_first_half")),
        team_b_second_half=_optional_int(payload.get("team_b_second_half")),
        player_stats=_parse_player_map_stats(raw_stats, players),
    )


def _parse_veto(payload: dict[str, Any]) -> CsParsedVeto:
    team_hltv_id = payload.get("team_hltv_id")
    return CsParsedVeto(
        order_idx=int(payload["order_idx"]),
        team_hltv_id=str(team_hltv_id) if team_hltv_id is not None else None,
        action=str(payload["action"]),
        map_name=normalize_map_name(str(payload["map_name"])),
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_player_map_stats(
    raw_stats: dict[str, Any],
    players: tuple[CsParsedPlayer, ...],
) -> tuple[CsParsedPlayerMapStats, ...]:
    if not isinstance(raw_stats, dict) or not raw_stats:
        return ()
    lookup = {player.nickname.lower(): player for player in players}
    result: list[CsParsedPlayerMapStats] = []
    for nickname, stats in raw_stats.items():
        if not isinstance(stats, dict):
            continue
        player = lookup.get(str(nickname).lower())
        if player is None:
            continue
        result.append(
            CsParsedPlayerMapStats(
                player_hltv_id=player.hltv_id,
                team_hltv_id=player.team_hltv_id,
                kills=_optional_int(stats.get("kills")),
                deaths=_optional_int(stats.get("deaths")),
                assists=_optional_int(stats.get("assists")),
                adr=_optional_float(stats.get("adr")),
                rating=_optional_float(stats.get("rating")),
                kast_pct=_optional_float(stats.get("kast_pct")),
                headshot_pct=_optional_float(stats.get("headshot_pct")),
                first_kills=_optional_int(stats.get("first_kills")),
                first_deaths=_optional_int(stats.get("first_deaths")),
                clutches_won=_optional_int(stats.get("clutches_won")),
                ct_kills=_optional_int(stats.get("ct_kills")),
                ct_deaths=_optional_int(stats.get("ct_deaths")),
                t_kills=_optional_int(stats.get("t_kills")),
                t_deaths=_optional_int(stats.get("t_deaths")),
                flash_assists=_optional_int(stats.get("flash_assists")),
                trade_deaths=_optional_int(stats.get("trade_deaths")),
            )
        )
    return tuple(result)


def _parse_head_to_head(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict) or not value:
        return None
    result: dict[str, int] = {}
    for key, raw_count in value.items():
        try:
            parsed_count = _optional_int(raw_count)
        except (TypeError, ValueError):
            return None
        if parsed_count is None:
            return None
        result[str(key)] = parsed_count
    return result or None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return float(value)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return bool(value)
