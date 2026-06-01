from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CsParsedTeam:
    hltv_id: str
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class CsParsedPlayer:
    hltv_id: str
    nickname: str
    team_hltv_id: str


@dataclass(frozen=True)
class CsParsedEvent:
    hltv_id: str
    name: str
    tier: str | None = None


@dataclass(frozen=True)
class CsParsedVeto:
    order_idx: int
    team_hltv_id: str | None
    action: str
    map_name: str


@dataclass(frozen=True)
class CsParsedPlayerMapStats:
    player_hltv_id: str
    team_hltv_id: str
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    adr: float | None = None
    rating: float | None = None
    kast_pct: float | None = None
    headshot_pct: float | None = None
    first_kills: int | None = None
    first_deaths: int | None = None
    clutches_won: int | None = None
    ct_kills: int | None = None
    ct_deaths: int | None = None
    t_kills: int | None = None
    t_deaths: int | None = None
    flash_assists: int | None = None
    trade_deaths: int | None = None


@dataclass(frozen=True)
class CsParsedMap:
    map_index: int
    map_name: str
    team_a_score: int
    team_b_score: int
    winner_hltv_id: str
    map_stats_id: str | None = None
    overtime: bool | None = None
    team_a_first_half: int | None = None
    team_a_second_half: int | None = None
    team_b_first_half: int | None = None
    team_b_second_half: int | None = None
    player_stats: tuple[CsParsedPlayerMapStats, ...] = ()


@dataclass(frozen=True)
class CsParsedMatch:
    hltv_id: str
    scheduled_at: datetime
    best_of: int
    status: str
    team_a: CsParsedTeam
    team_b: CsParsedTeam
    event: CsParsedEvent
    players: tuple[CsParsedPlayer, ...]
    maps: tuple[CsParsedMap, ...]
    vetoes: tuple[CsParsedVeto, ...]
    match_stage: str | None = None
    head_to_head: dict[str, int] | None = None
