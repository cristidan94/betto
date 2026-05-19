from __future__ import annotations

import json
import hashlib
import csv
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from core.edge import Recommendation, build_recommendation
from core.markets import MarketSnapshot
from sports.cs.models import BaselineMapWinnerModel, build_map_winner_dataset
from sports.cs.normalization.ids import cs_participant_id
from sports.cs.normalization.records import CsParsedMatch


@dataclass(frozen=True)
class CsMarketPriceFixture:
    contest_hltv_id: str
    map_index: int
    team_hltv_id: str
    best_bid: float
    best_ask: float
    taken_at: datetime
    close_price: float | None = None
    liquidity_usd: float | None = None
    resolved_team_hltv_id: str | None = None

    @property
    def team_id(self) -> str:
        return cs_participant_id("hltv", self.team_hltv_id)


@dataclass(frozen=True)
class PaperRecommendationResult:
    contest_hltv_id: str
    map_index: int
    team_id: str
    target: int
    features: dict[str, float | int | None]
    score_breakdown: dict[str, float]
    settlement_source: str
    settlement_mismatch: bool
    recommendation: Recommendation
    pnl_per_unit_stake: float | None
    clv: float | None


@dataclass(frozen=True)
class PaperEvaluationSummary:
    candidates: int
    recommendations: int
    mean_edge: float | None
    mean_clv: float | None
    hit_rate: float | None
    pnl_per_unit_stake: float
    roi_per_unit_stake: float | None
    max_drawdown_per_unit_stake: float
    total_bankroll_fraction: float
    max_bankroll_fraction: float | None
    mean_bankroll_fraction: float | None
    reason_counts: dict[str, int]
    daily_exposure: dict[str, dict[str, float | int]]
    per_match_exposure: dict[str, dict[str, float | int]]
    results: tuple[PaperRecommendationResult, ...]


def load_market_price_fixtures(path: Path) -> list[CsMarketPriceFixture]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("market fixture file must contain a list")
    return [_parse_price(row) for row in payload]


def load_market_price_corpus(path: Path) -> list[CsMarketPriceFixture]:
    if path.is_file():
        return load_market_price_fixtures(path)
    if not path.is_dir():
        raise ValueError(f"market fixture corpus path does not exist: {path}")
    fixtures = sorted(item for item in path.glob("*.json") if item.is_file())
    if not fixtures:
        raise ValueError(f"market fixture corpus has no JSON fixtures: {path}")
    prices: list[CsMarketPriceFixture] = []
    for fixture in fixtures:
        prices.extend(load_market_price_fixtures(fixture))
    return prices


def paper_evaluate_baseline(
    matches: list[CsParsedMatch],
    prices: list[CsMarketPriceFixture],
    min_edge: float,
    min_liquidity_usd: float = 0.0,
    max_recommendations_per_match: int | None = None,
    market_bankroll_cap: float = 0.04,
    max_daily_bankroll_fraction: float | None = None,
) -> PaperEvaluationSummary:
    _validate_paper_evaluation_controls(
        min_edge=min_edge,
        min_liquidity_usd=min_liquidity_usd,
        max_recommendations_per_match=max_recommendations_per_match,
        market_bankroll_cap=market_bankroll_cap,
        max_daily_bankroll_fraction=max_daily_bankroll_fraction,
    )
    rows = build_map_winner_dataset(matches)
    model = BaselineMapWinnerModel()
    price_lookup = {
        (price.contest_hltv_id, price.map_index, price.team_id): price
        for price in prices
    }
    results: list[PaperRecommendationResult] = []
    match_recommendation_counts: dict[str, int] = {}
    daily_bankroll_fractions: dict[str, float] = {}
    for row, score in zip(rows, model.score(rows), strict=True):
        price = price_lookup.get((row.contest_hltv_id, row.map_index, row.team_id))
        if price is None:
            continue
        fixture_target = _fixture_target(price)
        target = fixture_target if fixture_target is not None else row.target
        mismatch = fixture_target is not None and fixture_target != row.target
        snapshot = MarketSnapshot(
            market_id=f"fixture:{price.contest_hltv_id}:{price.map_index}:{price.team_id}",
            outcome=row.team_id,
            taken_at=price.taken_at,
            best_bid=price.best_bid,
            best_ask=price.best_ask,
        )
        recommendation = build_recommendation(
            snapshot,
            model_prob=score.probability,
            min_edge=min_edge,
            bankroll_cap=market_bankroll_cap,
        )
        if recommendation.passes_filter and price.liquidity_usd is not None and price.liquidity_usd < min_liquidity_usd:
            recommendation = replace(recommendation, passes_filter=False, reason="liquidity_below_threshold", bankroll_fraction=0.0)
        if recommendation.passes_filter and mismatch:
            recommendation = replace(recommendation, passes_filter=False, reason="settlement_mismatch", bankroll_fraction=0.0)
        if recommendation.passes_filter and max_recommendations_per_match is not None:
            used = match_recommendation_counts.get(row.contest_hltv_id, 0)
            if used >= max_recommendations_per_match:
                recommendation = replace(recommendation, passes_filter=False, reason="per_match_cap_reached", bankroll_fraction=0.0)
            else:
                match_recommendation_counts[row.contest_hltv_id] = used + 1
        if recommendation.passes_filter and max_daily_bankroll_fraction is not None:
            day = recommendation.taken_at.date().isoformat()
            used = daily_bankroll_fractions.get(day, 0.0)
            if used + recommendation.bankroll_fraction > max_daily_bankroll_fraction:
                recommendation = replace(recommendation, passes_filter=False, reason="daily_cap_reached", bankroll_fraction=0.0)
            else:
                daily_bankroll_fractions[day] = used + recommendation.bankroll_fraction
        pnl = _pnl_per_unit_stake(recommendation.market_prob, target) if recommendation.passes_filter else None
        clv = (price.close_price - recommendation.market_prob) if recommendation.passes_filter and price.close_price is not None else None
        results.append(
            PaperRecommendationResult(
                contest_hltv_id=row.contest_hltv_id,
                map_index=row.map_index,
                team_id=row.team_id,
                target=target,
                features=dict(row.features),
                score_breakdown=asdict(score),
                settlement_source="fixture" if fixture_target is not None else "match_result",
                settlement_mismatch=mismatch,
                recommendation=recommendation,
                pnl_per_unit_stake=pnl,
                clv=clv,
            )
        )
    passing = [result for result in results if result.recommendation.passes_filter]
    mean_edge = sum(result.recommendation.edge for result in passing) / len(passing) if passing else None
    clv_values = [result.clv for result in passing if result.clv is not None]
    mean_clv = sum(clv_values) / len(clv_values) if clv_values else None
    hit_rate = sum(result.target for result in passing) / len(passing) if passing else None
    pnl = sum(result.pnl_per_unit_stake or 0.0 for result in passing)
    roi = pnl / len(passing) if passing else None
    bankroll_fractions = [result.recommendation.bankroll_fraction for result in passing]
    total_bankroll_fraction = sum(bankroll_fractions)
    max_bankroll_fraction = max(bankroll_fractions) if bankroll_fractions else None
    mean_bankroll_fraction = total_bankroll_fraction / len(bankroll_fractions) if bankroll_fractions else None
    reason_counts: dict[str, int] = {}
    for result in results:
        reason_counts[result.recommendation.reason] = reason_counts.get(result.recommendation.reason, 0) + 1
    daily_exposure = _daily_exposure(passing)
    per_match_exposure = _per_match_exposure(passing)
    max_drawdown = _max_drawdown_per_unit_stake(passing)
    return PaperEvaluationSummary(
        candidates=len(results),
        recommendations=len(passing),
        mean_edge=mean_edge,
        mean_clv=mean_clv,
        hit_rate=hit_rate,
        pnl_per_unit_stake=pnl,
        roi_per_unit_stake=roi,
        max_drawdown_per_unit_stake=max_drawdown,
        total_bankroll_fraction=total_bankroll_fraction,
        max_bankroll_fraction=max_bankroll_fraction,
        mean_bankroll_fraction=mean_bankroll_fraction,
        reason_counts=reason_counts,
        daily_exposure=daily_exposure,
        per_match_exposure=per_match_exposure,
        results=tuple(results),
    )


def paper_evaluation_payload(summary: PaperEvaluationSummary) -> dict[str, object]:
    return {
        "candidates": summary.candidates,
        "recommendations": summary.recommendations,
        "mean_edge": summary.mean_edge,
        "mean_clv": summary.mean_clv,
        "hit_rate": summary.hit_rate,
        "pnl_per_unit_stake": summary.pnl_per_unit_stake,
        "roi_per_unit_stake": summary.roi_per_unit_stake,
        "max_drawdown_per_unit_stake": summary.max_drawdown_per_unit_stake,
        "total_bankroll_fraction": summary.total_bankroll_fraction,
        "max_bankroll_fraction": summary.max_bankroll_fraction,
        "mean_bankroll_fraction": summary.mean_bankroll_fraction,
        "reason_counts": summary.reason_counts,
        "daily_exposure": summary.daily_exposure,
        "per_match_exposure": summary.per_match_exposure,
        "results": [
            _recommendation_result_payload(result)
            for result in summary.results
        ],
    }


def compact_paper_evaluation_payload(summary: PaperEvaluationSummary) -> dict[str, object]:
    payload = paper_evaluation_payload(summary)
    payload.pop("results", None)
    return payload


def accepted_paper_recommendations_payload(summary: PaperEvaluationSummary, max_items: int | None = None) -> dict[str, object]:
    accepted = _ranked_accepted_results(summary)
    if max_items is not None:
        accepted = accepted[:max_items]
    return {
        "summary": compact_paper_evaluation_payload(summary),
        "recommendations": [
            _recommendation_result_payload(result, review_rank=index)
            for index, result in enumerate(accepted, start=1)
        ],
    }


def accepted_paper_recommendations_digest(summary: PaperEvaluationSummary, max_items: int | None = None) -> dict[str, object]:
    accepted = _ranked_accepted_results(summary)
    if max_items is not None:
        accepted = accepted[:max_items]
    return {
        "summary": {
            "candidates": summary.candidates,
            "recommendations": summary.recommendations,
            "mean_edge": summary.mean_edge,
            "total_bankroll_fraction": summary.total_bankroll_fraction,
            "max_drawdown_per_unit_stake": summary.max_drawdown_per_unit_stake,
            "reason_counts": summary.reason_counts,
        },
        "recommendations": [
            {
                "review_rank": index,
                "contest_hltv_id": result.contest_hltv_id,
                "map_index": result.map_index,
                "team_id": result.team_id,
                "model_prob": result.recommendation.model_prob,
                "market_prob": result.recommendation.market_prob,
                "edge": result.recommendation.edge,
                "bankroll_fraction": result.recommendation.bankroll_fraction,
                "action_score": _action_score(result),
                "clv": result.clv,
                "pnl_per_unit_stake": result.pnl_per_unit_stake,
            }
            for index, result in enumerate(accepted, start=1)
        ],
    }


def write_paper_evaluation_artifact(summary: PaperEvaluationSummary, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = paper_evaluation_payload(summary)
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    path = output_dir / f"cs-paper-evaluation-{digest}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def write_accepted_paper_recommendations_artifact(summary: PaperEvaluationSummary, output_dir: Path, max_items: int | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = accepted_paper_recommendations_payload(summary, max_items=max_items)
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    path = output_dir / f"cs-accepted-paper-recommendations-{digest}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def write_paper_recommendations_csv(summary: PaperEvaluationSummary, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(paper_evaluation_payload(summary), sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    path = output_dir / f"cs-paper-recommendations-{digest}.csv"
    _write_recommendation_rows_csv(path, summary.results)
    return path


def write_accepted_paper_recommendations_csv(summary: PaperEvaluationSummary, output_dir: Path, max_items: int | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = accepted_paper_recommendations_payload(summary, max_items=max_items)
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    path = output_dir / f"cs-accepted-paper-recommendations-{digest}.csv"
    accepted = _ranked_accepted_results(summary)
    if max_items is not None:
        accepted = accepted[:max_items]
    _write_recommendation_rows_csv(path, accepted, include_review_rank=True)
    return path


def _write_recommendation_rows_csv(path: Path, results: tuple[PaperRecommendationResult, ...], include_review_rank: bool = False) -> None:
    fieldnames = [
        "contest_hltv_id",
        "map_index",
        "team_id",
        "target",
        "passes_filter",
        "reason",
        "model_prob",
        "market_prob",
        "edge",
        "bankroll_fraction",
        "clv",
        "pnl_per_unit_stake",
        "settlement_source",
        "settlement_mismatch",
        "action_score",
        "best_of",
        "team_maps_played_90d",
        "opponent_maps_played_90d",
        "map_win_rate_diff_90d",
        "team_rest_days",
        "opponent_rest_days",
        "rest_days_diff",
        "sample_confidence",
        "shrink_multiplier",
        "best_of_multiplier",
        "map_strength_logit",
        "rest_days_logit",
        "total_logit",
    ]
    if include_review_rank:
        fieldnames.insert(0, "review_rank")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, result in enumerate(results, start=1):
            row = {
                "contest_hltv_id": result.contest_hltv_id,
                "map_index": result.map_index,
                "team_id": result.team_id,
                "target": result.target,
                "passes_filter": result.recommendation.passes_filter,
                "reason": result.recommendation.reason,
                "model_prob": result.recommendation.model_prob,
                "market_prob": result.recommendation.market_prob,
                "edge": result.recommendation.edge,
                "bankroll_fraction": result.recommendation.bankroll_fraction,
                "clv": result.clv,
                "pnl_per_unit_stake": result.pnl_per_unit_stake,
                "settlement_source": result.settlement_source,
                "settlement_mismatch": result.settlement_mismatch,
                "action_score": _action_score(result),
                "best_of": result.features.get("best_of"),
                "team_maps_played_90d": result.features.get("team_maps_played_90d"),
                "opponent_maps_played_90d": result.features.get("opponent_maps_played_90d"),
                "map_win_rate_diff_90d": result.features.get("map_win_rate_diff_90d"),
                "team_rest_days": result.features.get("team_rest_days"),
                "opponent_rest_days": result.features.get("opponent_rest_days"),
                "rest_days_diff": result.features.get("rest_days_diff"),
                "sample_confidence": result.score_breakdown.get("sample_confidence"),
                "shrink_multiplier": result.score_breakdown.get("shrink_multiplier"),
                "best_of_multiplier": result.score_breakdown.get("best_of_multiplier"),
                "map_strength_logit": result.score_breakdown.get("map_strength_logit"),
                "rest_days_logit": result.score_breakdown.get("rest_days_logit"),
                "total_logit": result.score_breakdown.get("total_logit"),
            }
            if include_review_rank:
                row["review_rank"] = index
            writer.writerow(row)


def _parse_price(row: dict[str, object]) -> CsMarketPriceFixture:
    taken_at_raw = str(row["taken_at"])
    taken_at = datetime.fromisoformat(taken_at_raw.replace("Z", "+00:00"))
    if taken_at.tzinfo is None:
        taken_at = taken_at.replace(tzinfo=timezone.utc)
    return CsMarketPriceFixture(
        contest_hltv_id=str(row["contest_hltv_id"]),
        map_index=int(row["map_index"]),
        team_hltv_id=str(row["team_hltv_id"]),
        best_bid=float(row["best_bid"]),
        best_ask=float(row["best_ask"]),
        taken_at=taken_at,
        close_price=_optional_float(row.get("close_price")),
        liquidity_usd=_optional_float(row.get("liquidity_usd")),
        resolved_team_hltv_id=str(row["resolved_team_hltv_id"]) if row.get("resolved_team_hltv_id") is not None else None,
    )


def _pnl_per_unit_stake(price: float, target: int) -> float:
    if target == 1:
        return (1 / price) - 1
    return -1.0


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _fixture_target(price: CsMarketPriceFixture) -> int | None:
    if price.resolved_team_hltv_id is None:
        return None
    return 1 if price.resolved_team_hltv_id == price.team_hltv_id else 0


def _validate_paper_evaluation_controls(
    min_edge: float,
    min_liquidity_usd: float,
    max_recommendations_per_match: int | None,
    market_bankroll_cap: float,
    max_daily_bankroll_fraction: float | None,
) -> None:
    if not 0 <= min_edge <= 1:
        raise ValueError("min_edge must be between 0 and 1")
    if min_liquidity_usd < 0:
        raise ValueError("min_liquidity_usd must be non-negative")
    if max_recommendations_per_match is not None and max_recommendations_per_match <= 0:
        raise ValueError("max_recommendations_per_match must be positive when set")
    if not 0 < market_bankroll_cap <= 1:
        raise ValueError("market_bankroll_cap must be in (0, 1]")
    if max_daily_bankroll_fraction is not None and not 0 < max_daily_bankroll_fraction <= 1:
        raise ValueError("max_daily_bankroll_fraction must be in (0, 1] when set")


def _recommendation_result_payload(result: PaperRecommendationResult, review_rank: int | None = None) -> dict[str, object]:
    recommendation = asdict(result.recommendation)
    recommendation["taken_at"] = result.recommendation.taken_at.isoformat()
    payload = {
        "contest_hltv_id": result.contest_hltv_id,
        "map_index": result.map_index,
        "team_id": result.team_id,
        "target": result.target,
        "action_score": _action_score(result),
        "features": result.features,
        "score_breakdown": result.score_breakdown,
        "settlement_source": result.settlement_source,
        "settlement_mismatch": result.settlement_mismatch,
        "pnl_per_unit_stake": result.pnl_per_unit_stake,
        "clv": result.clv,
        "recommendation": recommendation,
    }
    if review_rank is not None:
        payload["review_rank"] = review_rank
    return payload


def _ranked_accepted_results(summary: PaperEvaluationSummary) -> tuple[PaperRecommendationResult, ...]:
    return tuple(
        sorted(
            (result for result in summary.results if result.recommendation.passes_filter),
            key=lambda result: (_action_score(result), result.recommendation.edge, result.recommendation.bankroll_fraction),
            reverse=True,
        )
    )


def _action_score(result: PaperRecommendationResult) -> float:
    if not result.recommendation.passes_filter:
        return 0.0
    return result.recommendation.edge * result.recommendation.bankroll_fraction


def _per_match_exposure(results: list[PaperRecommendationResult]) -> dict[str, dict[str, float | int]]:
    exposure: dict[str, dict[str, float | int]] = {}
    for result in results:
        current = exposure.setdefault(
            result.contest_hltv_id,
            {
                "recommendations": 0,
                "total_bankroll_fraction": 0.0,
                "pnl_per_unit_stake": 0.0,
                "edge_sum": 0.0,
            },
        )
        current["recommendations"] = int(current["recommendations"]) + 1
        current["total_bankroll_fraction"] = float(current["total_bankroll_fraction"]) + result.recommendation.bankroll_fraction
        current["pnl_per_unit_stake"] = float(current["pnl_per_unit_stake"]) + (result.pnl_per_unit_stake or 0.0)
        current["edge_sum"] = float(current["edge_sum"]) + result.recommendation.edge
    for current in exposure.values():
        recommendations = int(current["recommendations"])
        current["mean_edge"] = float(current["edge_sum"]) / recommendations if recommendations else 0.0
        del current["edge_sum"]
    return exposure


def _daily_exposure(results: list[PaperRecommendationResult]) -> dict[str, dict[str, float | int]]:
    exposure: dict[str, dict[str, float | int]] = {}
    for result in results:
        day = result.recommendation.taken_at.date().isoformat()
        current = exposure.setdefault(
            day,
            {
                "recommendations": 0,
                "total_bankroll_fraction": 0.0,
                "pnl_per_unit_stake": 0.0,
                "edge_sum": 0.0,
            },
        )
        current["recommendations"] = int(current["recommendations"]) + 1
        current["total_bankroll_fraction"] = float(current["total_bankroll_fraction"]) + result.recommendation.bankroll_fraction
        current["pnl_per_unit_stake"] = float(current["pnl_per_unit_stake"]) + (result.pnl_per_unit_stake or 0.0)
        current["edge_sum"] = float(current["edge_sum"]) + result.recommendation.edge
    for current in exposure.values():
        recommendations = int(current["recommendations"])
        current["mean_edge"] = float(current["edge_sum"]) / recommendations if recommendations else 0.0
        del current["edge_sum"]
    return dict(sorted(exposure.items()))


def _max_drawdown_per_unit_stake(results: list[PaperRecommendationResult]) -> float:
    peak = 0.0
    equity = 0.0
    max_drawdown = 0.0
    for result in sorted(results, key=lambda item: item.recommendation.taken_at):
        equity += result.pnl_per_unit_stake or 0.0
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown
