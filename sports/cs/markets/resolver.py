from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ContestCandidate:
    contest_id: str
    starts_at: datetime
    team_a_names: tuple[str, ...]
    team_b_names: tuple[str, ...]
    event_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketResolution:
    contest_id: str | None
    confidence: float
    reason: str
    manual_review: bool
    outcome_mapping: dict[str, str] | None


def resolve_market(
    question: str,
    candidates: list[ContestCandidate],
    outcomes: tuple[str, ...] = (),
    starts_at_hint: datetime | None = None,
    confidence_threshold: float = 0.72,
    ambiguity_margin: float = 0.08,
) -> MarketResolution:
    scored = sorted(
        ((_score_candidate(question, candidate, starts_at_hint), candidate) for candidate in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored or scored[0][0] <= 0:
        return MarketResolution(None, 0.0, "no_match", True, None)

    best_score, best = scored[0]
    if len(scored) > 1 and best_score - scored[1][0] < ambiguity_margin:
        return MarketResolution(None, best_score, "ambiguous_match", True, None)

    mapping = _map_outcomes(outcomes, best)
    manual_review = best_score < confidence_threshold or mapping is None
    reason = "linked" if not manual_review else "low_confidence"
    return MarketResolution(best.contest_id, best_score, reason, manual_review, mapping)


def _score_candidate(question: str, candidate: ContestCandidate, starts_at_hint: datetime | None) -> float:
    normalized_question = _normalize(question)
    team_a_score = max((_contains_name(normalized_question, name) for name in candidate.team_a_names), default=0.0)
    team_b_score = max((_contains_name(normalized_question, name) for name in candidate.team_b_names), default=0.0)
    if team_a_score == 0 or team_b_score == 0:
        return 0.0

    event_score = max((_contains_name(normalized_question, name) for name in candidate.event_names), default=0.0)
    time_score = _time_score(candidate.starts_at, starts_at_hint)
    return min(1.0, 0.42 * team_a_score + 0.42 * team_b_score + 0.10 * event_score + 0.06 * time_score)


def _contains_name(normalized_question: str, name: str) -> float:
    normalized_name = _normalize(name)
    if not normalized_name:
        return 0.0
    if f" {normalized_name} " in f" {normalized_question} ":
        return 1.0
    name_tokens = set(normalized_name.split())
    question_tokens = set(normalized_question.split())
    if not name_tokens:
        return 0.0
    overlap = len(name_tokens & question_tokens) / len(name_tokens)
    return overlap if overlap >= 0.67 else 0.0


def _time_score(starts_at: datetime, hint: datetime | None) -> float:
    if hint is None:
        return 0.5
    delta = abs(starts_at - hint)
    if delta <= timedelta(hours=2):
        return 1.0
    if delta <= timedelta(hours=12):
        return 0.6
    if delta <= timedelta(days=2):
        return 0.25
    return 0.0


def _map_outcomes(outcomes: tuple[str, ...], candidate: ContestCandidate) -> dict[str, str] | None:
    if not outcomes:
        return None
    mapping: dict[str, str] = {}
    for outcome in outcomes:
        normalized = _normalize(outcome)
        if any(_contains_name(normalized, name) for name in candidate.team_a_names):
            mapping[outcome] = "team_a"
        elif any(_contains_name(normalized, name) for name in candidate.team_b_names):
            mapping[outcome] = "team_b"
    return mapping if len(mapping) == len(outcomes) else None


def _normalize(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()
