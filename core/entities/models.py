from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ParticipantKind(StrEnum):
    TEAM = "team"
    PLAYER = "player"
    ORGANIZATION = "organization"


@dataclass(frozen=True)
class Participant:
    participant_id: str
    game_id: str
    kind: ParticipantKind
    display_name: str
    source: str
    source_id: str


@dataclass(frozen=True)
class Competition:
    competition_id: str
    game_id: str
    name: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    tier: str | None = None


@dataclass(frozen=True)
class Contest:
    contest_id: str
    game_id: str
    competition_id: str | None
    starts_at: datetime
    participant_a_id: str
    participant_b_id: str
    format: str
    status: str
    match_stage: str | None = None
    head_to_head: dict[str, int] | None = None


@dataclass(frozen=True)
class ContestUnit:
    unit_id: str
    contest_id: str
    sequence_number: int
    unit_type: str
    name: str | None = None
    winner_id: str | None = None


@dataclass(frozen=True)
class RosterSnapshot:
    roster_id: str
    participant_id: str
    player_ids: tuple[str, ...]
    as_of: datetime
    source: str
