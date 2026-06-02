from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from core.entities import Contest, Participant


@dataclass(frozen=True)
class LinkCandidate:
    contest_id: str
    confidence: float
    matched_teams: tuple[str, str]


# Common CS2 team name aliases (display_name -> known aliases)
TEAM_ALIASES: dict[str, tuple[str, ...]] = {
    "natus vincere": ("navi", "na'vi", "natus vincere"),
    "g2 esports": ("g2",),
    "team vitality": ("vitality", "vita"),
    "faze clan": ("faze",),
    "team liquid": ("liquid", "tl"),
    "cloud9": ("c9",),
    "heroic": ("heroic",),
    "mouz": ("mouz", "mousesports"),
    "virtus.pro": ("vp", "virtus pro", "virtuspro"),
    "ninjas in pyjamas": ("nip",),
    "astralis": ("astralis",),
    "ence": ("ence",),
    "complexity gaming": ("complexity", "col"),
    "big": ("big",),
    "monte": ("monte",),
    "the mongolz": ("mongolz", "the mongolz"),
    "spirit": ("spirit", "team spirit"),
    "eternal fire": ("ef", "eternal fire"),
    "3dmax": ("3dmax",),
    "apeks": ("apeks",),
    "betboom team": ("betboom",),
    "pain gaming": ("pain",),
    "imperial esports": ("imperial",),
    "tyloo": ("tyloo",),
    "lynn vision": ("lynn vision",),
    "rare atom": ("rare atom",),
    "wildcard gaming": ("wildcard",),
    "saw": ("saw",),
    "pgl": ("pgl",),
}

_VS_PATTERN = re.compile(
    r"(?:will\s+)?(.+?)\s+(?:win|beat|defeat)\s+(?:(?:map\s*\d+\s*)?(?:vs\.?|versus|against|over)\s+)?(.+?)(?:\s+in\s+.+)?(?:\s*\?|$)",
    re.IGNORECASE,
)

_VERSUS_SPLIT = re.compile(r"\s+vs\.?\s+|\s+versus\s+", re.IGNORECASE)


def extract_team_names(question: str) -> tuple[str, str] | None:
    """Extract two team name candidates from a Polymarket question string."""
    match = _VS_PATTERN.search(question)
    if match:
        a = _clean_team_name(match.group(1))
        b = _clean_team_name(match.group(2))
        if a and b:
            return (a, b)

    parts = _VERSUS_SPLIT.split(question, maxsplit=1)
    if len(parts) == 2:
        a = _clean_team_name(parts[0])
        b = _clean_team_name(parts[1].rstrip("?").strip())
        if a and b:
            return (a, b)

    return None


def _clean_team_name(name: str) -> str:
    name = re.sub(r"\b(map\s*\d+|counter[- ]?strike\s*2?|cs2|csgo)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip(" -?,.")
    return name


def _normalize_for_match(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _name_matches(candidate: str, display_name: str) -> bool:
    """Check if a candidate name matches a known team display name or alias."""
    norm_candidate = _normalize_for_match(candidate)
    if not norm_candidate:
        return False

    norm_display = _normalize_for_match(display_name)
    if norm_candidate == norm_display or norm_candidate in norm_display or norm_display in norm_candidate:
        return True

    for known_name, aliases in TEAM_ALIASES.items():
        norm_known = _normalize_for_match(known_name)
        norm_aliases = {_normalize_for_match(a) for a in aliases}
        all_norms = norm_aliases | {norm_known}
        if norm_display in all_norms or any(norm_display in n or n in norm_display for n in all_norms):
            if norm_candidate in all_norms or any(norm_candidate in n or n in norm_candidate for n in all_norms):
                return True

    return False


def link_market_to_contest(
    question: str,
    participants: list[Participant],
    contests: list[Contest],
    market_end_date: datetime | None = None,
) -> LinkCandidate | None:
    """Try to link a Polymarket question to a known contest.

    Returns the best matching contest with a confidence score, or None if no match.
    """
    names = extract_team_names(question)
    if names is None:
        return None

    name_a, name_b = names
    match_a: Participant | None = None
    match_b: Participant | None = None

    for p in participants:
        if p.kind.value != "team":
            continue
        if match_a is None and _name_matches(name_a, p.display_name):
            match_a = p
        if match_b is None and _name_matches(name_b, p.display_name):
            match_b = p
        if match_a and match_b:
            break

    if match_a is None or match_b is None:
        return None

    best: LinkCandidate | None = None
    for contest in contests:
        ids = {contest.participant_a_id, contest.participant_b_id}
        if match_a.participant_id in ids and match_b.participant_id in ids:
            confidence = 0.8
            if market_end_date and abs((contest.starts_at - market_end_date).total_seconds()) < 86400:
                confidence = 0.95
            if best is None or confidence > best.confidence:
                best = LinkCandidate(
                    contest_id=contest.contest_id,
                    confidence=confidence,
                    matched_teams=(match_a.display_name, match_b.display_name),
                )

    return best
