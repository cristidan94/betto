from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "hltv-fixture-v1"


@dataclass(frozen=True)
class ScrapedTeam:
    hltv_id: str
    name: str


@dataclass(frozen=True)
class ScrapedPlayer:
    hltv_id: str
    nickname: str
    team_hltv_id: str


@dataclass(frozen=True)
class ScrapedEvent:
    hltv_id: str
    name: str
    stars: int | None = None
    priority_tier: int | None = None


@dataclass(frozen=True)
class ScrapedPlayerMapStats:
    player_hltv_id: str
    nickname: str
    team_hltv_id: str
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    adr: float | None = None
    rating: float | None = None
    headshot_pct: float | None = None
    kast_pct: float | None = None
    first_kills: int | None = None
    first_deaths: int | None = None
    ct_kills: int | None = None
    ct_deaths: int | None = None
    t_kills: int | None = None
    t_deaths: int | None = None
    clutches_won: int | None = None
    # Detailed fields available only from the /stats/ map page (via unblocker).
    hs_kills: int | None = None
    multi_kills: int | None = None
    flash_assists: int | None = None
    trade_deaths: int | None = None


@dataclass(frozen=True)
class ScrapedMap:
    map_index: int
    map_name: str
    team_a_score: int
    team_b_score: int
    winner_hltv_id: str
    map_stats_id: str | None = None
    team_a_first_half: int | None = None
    team_b_first_half: int | None = None
    team_a_second_half: int | None = None
    team_b_second_half: int | None = None
    overtime: bool = False
    player_stats: tuple[ScrapedPlayerMapStats, ...] = ()


@dataclass(frozen=True)
class ScrapedVeto:
    order_idx: int
    team_hltv_id: str | None
    action: str
    map_name: str


@dataclass(frozen=True)
class ScrapedMatch:
    hltv_id: str
    scheduled_at: datetime
    best_of: int
    status: str
    team_a: ScrapedTeam
    team_b: ScrapedTeam
    event: ScrapedEvent
    players: tuple[ScrapedPlayer, ...]
    maps: tuple[ScrapedMap, ...]
    vetoes: tuple[ScrapedVeto, ...]
    stats_url: str | None = None
    match_stage: str | None = None
    head_to_head: dict | None = None


def match_to_fixture_json(match: ScrapedMatch) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "hltv_id": match.hltv_id,
        "scheduled_at": match.scheduled_at.isoformat(),
        "best_of": match.best_of,
        "status": match.status,
        "team_a": {"hltv_id": match.team_a.hltv_id, "name": match.team_a.name},
        "team_b": {"hltv_id": match.team_b.hltv_id, "name": match.team_b.name},
        "event": {
            "hltv_id": match.event.hltv_id,
            "name": match.event.name,
            "tier": match.event.priority_tier if match.event.priority_tier is not None else _tier_from_stars(match.event.stars),
            "hltv_stars": match.event.stars,
        },
        "players": [
            {"hltv_id": p.hltv_id, "nickname": p.nickname, "team_hltv_id": p.team_hltv_id}
            for p in match.players
        ],
        "match_stage": match.match_stage,
        "head_to_head": match.head_to_head,
        "maps": [
            {
                "map_index": m.map_index,
                "map_name": m.map_name,
                "map_stats_id": m.map_stats_id,
                "team_a_score": m.team_a_score,
                "team_b_score": m.team_b_score,
                "winner_hltv_id": m.winner_hltv_id,
                "team_a_first_half": m.team_a_first_half,
                "team_b_first_half": m.team_b_first_half,
                "team_a_second_half": m.team_a_second_half,
                "team_b_second_half": m.team_b_second_half,
                "overtime": m.overtime,
                "player_stats": {
                    ps.nickname: {
                        "kills": ps.kills,
                        "deaths": ps.deaths,
                        "assists": ps.assists,
                        "adr": ps.adr,
                        "rating": ps.rating,
                        "headshot_pct": ps.headshot_pct,
                        "kast_pct": ps.kast_pct,
                        "first_kills": ps.first_kills,
                        "first_deaths": ps.first_deaths,
                        "ct_kills": ps.ct_kills,
                        "ct_deaths": ps.ct_deaths,
                        "t_kills": ps.t_kills,
                        "t_deaths": ps.t_deaths,
                        "clutches_won": ps.clutches_won,
                        "hs_kills": ps.hs_kills,
                        "multi_kills": ps.multi_kills,
                        "flash_assists": ps.flash_assists,
                        "trade_deaths": ps.trade_deaths,
                    }
                    for ps in m.player_stats
                },
            }
            for m in match.maps
        ],
        "vetoes": [
            {
                "order_idx": v.order_idx,
                "team_hltv_id": v.team_hltv_id,
                "action": v.action,
                "map_name": v.map_name,
            }
            for v in match.vetoes
        ],
        "source": {
            "name": "hltv-scraper",
            "url": f"https://www.hltv.org/matches/{match.hltv_id}",
            "stats_url": match.stats_url,
        },
    }


def write_fixture_json(match: ScrapedMatch, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{match.hltv_id}.json"
    path.write_text(json.dumps(match_to_fixture_json(match), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _tier_from_stars(stars: int | None) -> int | None:
    if stars is None:
        return None
    return max(1, 6 - stars)
