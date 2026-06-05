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

# Words that mean the extracted phrase is a tournament/award/stage, not a team.
_NON_TEAM_RE = re.compile(
    r"\b(tournament|championship|champions?|major|qualifier|cup|league|season|"
    r"stage|group|playoff|final|finals|series|award|bracket|swiss|grand)\b",
    re.IGNORECASE,
)

# Leading event/league labels precede the actual matchup, e.g. "IEM Cologne: A vs B".
_VS_OR_BEAT_RE = re.compile(r"\b(vs\.?|versus|beat|defeat|win)\b", re.IGNORECASE)


def _strip_event_prefix(question: str) -> str:
    """Drop a leading "Event Name:" label so only the "A vs B" clause remains."""
    if ":" in question:
        head, _, tail = question.partition(":")
        if tail.strip() and not _VS_OR_BEAT_RE.search(head):
            return tail.strip()
    return question


def _plausible_team(name: str) -> bool:
    if not name or len(name) > 30:
        return False
    if _NON_TEAM_RE.search(name):
        return False
    if len(name.split()) > 4:
        return False
    return True


def extract_team_names(question: str) -> tuple[str, str] | None:
    """Extract two team name candidates from a Polymarket question string."""
    question = _strip_event_prefix(question)

    a: str | None = None
    b: str | None = None

    match = _VS_PATTERN.search(question)
    if match:
        a = _clean_team_name(match.group(1))
        b = _clean_team_name(match.group(2))

    if not (a and b):
        parts = _VERSUS_SPLIT.split(question, maxsplit=1)
        if len(parts) == 2:
            a = _clean_team_name(parts[0])
            b = _clean_team_name(parts[1].rstrip("?").strip())

    if a and b and _plausible_team(a) and _plausible_team(b):
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

    # A real matchup is between two different teams; a single team matching both
    # parsed names (via a loose alias) is a false positive.
    if match_a.participant_id == match_b.participant_id:
        return None

    # The same two teams may meet many times. Among all contests featuring both,
    # prefer the one closest in time to the market's date so repeat matchups don't
    # get linked to an arbitrary (first-scanned) meeting.
    best: LinkCandidate | None = None
    best_gap: float | None = None
    for contest in contests:
        ids = {contest.participant_a_id, contest.participant_b_id}
        if match_a.participant_id not in ids or match_b.participant_id not in ids:
            continue

        gap: float | None = None
        if market_end_date is not None and contest.starts_at is not None:
            gap = abs((contest.starts_at - market_end_date).total_seconds())
        confidence = 0.95 if (gap is not None and gap < 86400) else 0.8

        better = False
        if best is None:
            better = True
        elif confidence > best.confidence:
            better = True
        elif confidence == best.confidence and gap is not None and (best_gap is None or gap < best_gap):
            better = True

        if better:
            best = LinkCandidate(
                contest_id=contest.contest_id,
                confidence=confidence,
                matched_teams=(match_a.display_name, match_b.display_name),
            )
            best_gap = gap

    return best
