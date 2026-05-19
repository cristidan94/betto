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
class CsParsedMap:
    map_index: int
    map_name: str
    team_a_score: int
    team_b_score: int
    winner_hltv_id: str


@dataclass(frozen=True)
class CsParsedVeto:
    order_idx: int
    team_hltv_id: str | None
    action: str
    map_name: str


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

