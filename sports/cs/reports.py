from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.modeling import brier_score, expected_calibration_error, log_loss
from sports.cs.fixtures import load_fixture_corpus
from sports.cs.markets import load_market_price_corpus, paper_evaluate_baseline, paper_evaluation_payload
from sports.cs.models import BaselineMapWinnerModel, build_map_winner_dataset


def build_baseline_strategy_report(
    fixture_corpus: Path,
    market_corpus: Path,
    min_edge: float,
    min_liquidity_usd: float = 0.0,
    max_recommendations_per_match: int | None = None,
    market_bankroll_cap: float = 0.04,
    max_daily_bankroll_fraction: float | None = None,
    max_brier_score: float = 0.30,
    max_log_loss: float = 0.80,
    max_total_bankroll_fraction: float = 0.25,
    max_drawdown_per_unit_stake: float = 3.0,
    min_paper_recommendations: int = 1,
    min_mean_edge: float = 0.03,
) -> dict[str, object]:
    matches = load_fixture_corpus(fixture_corpus)
    rows = build_map_winner_dataset(matches)
    if not rows:
        raise ValueError("no baseline dataset rows could be built")
    model = BaselineMapWinnerModel()
    predictions = model.predict(rows)
    targets = [row.target for row in rows]
    prices = load_market_price_corpus(market_corpus)
    paper_summary = paper_evaluate_baseline(
        matches,
        prices,
        min_edge=min_edge,
        min_liquidity_usd=min_liquidity_usd,
        max_recommendations_per_match=max_recommendations_per_match,
        market_bankroll_cap=market_bankroll_cap,
        max_daily_bankroll_fraction=max_daily_bankroll_fraction,
    )
    model_metrics = {
        "brier_score": brier_score(predictions, targets),
        "log_loss": log_loss(predictions, targets),
        "expected_calibration_error": expected_calibration_error(predictions, targets),
    }
    paper_payload = paper_evaluation_payload(paper_summary)
    readiness = _readiness_checks(
        model_metrics=model_metrics,
        paper_payload=paper_payload,
        max_brier_score=max_brier_score,
        max_log_loss=max_log_loss,
        max_total_bankroll_fraction=max_total_bankroll_fraction,
        max_drawdown_per_unit_stake=max_drawdown_per_unit_stake,
        min_paper_recommendations=min_paper_recommendations,
        min_mean_edge=min_mean_edge,
    )
    return {
        "strategy_id": "cs_baseline_fixture_v1",
        "fixture_corpus": str(fixture_corpus),
        "market_corpus": str(market_corpus),
        "model": {
            "target": "cs.map_winner",
            "rows": len(rows),
            "metrics": model_metrics,
        },
        "paper": paper_payload,
        "readiness": readiness,
    }


def write_strategy_report(report: dict[str, object], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    path = output_dir / f"cs-baseline-strategy-report-{digest}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def compact_strategy_report(report: dict[str, object]) -> dict[str, object]:
    paper = dict(report["paper"])  # type: ignore[arg-type]
    paper.pop("results", None)
    return {
        "strategy_id": report["strategy_id"],
        "model": report["model"],
        "paper": paper,
        "readiness": report["readiness"],
    }


def _readiness_checks(
    model_metrics: dict[str, float],
    paper_payload: dict[str, object],
    max_brier_score: float,
    max_log_loss: float,
    max_total_bankroll_fraction: float,
    max_drawdown_per_unit_stake: float,
    min_paper_recommendations: int,
    min_mean_edge: float,
) -> dict[str, object]:
    checks = [
        {
            "name": "brier_score",
            "passed": model_metrics["brier_score"] <= max_brier_score,
            "value": model_metrics["brier_score"],
            "threshold": max_brier_score,
            "direction": "max",
        },
        {
            "name": "log_loss",
            "passed": model_metrics["log_loss"] <= max_log_loss,
            "value": model_metrics["log_loss"],
            "threshold": max_log_loss,
            "direction": "max",
        },
        {
            "name": "paper_recommendations",
            "passed": int(paper_payload["recommendations"]) >= min_paper_recommendations,
            "value": paper_payload["recommendations"],
            "threshold": min_paper_recommendations,
            "direction": "min",
        },
        {
            "name": "total_bankroll_fraction",
            "passed": float(paper_payload["total_bankroll_fraction"]) <= max_total_bankroll_fraction,
            "value": paper_payload["total_bankroll_fraction"],
            "threshold": max_total_bankroll_fraction,
            "direction": "max",
        },
        {
            "name": "max_drawdown_per_unit_stake",
            "passed": float(paper_payload["max_drawdown_per_unit_stake"]) <= max_drawdown_per_unit_stake,
            "value": paper_payload["max_drawdown_per_unit_stake"],
            "threshold": max_drawdown_per_unit_stake,
            "direction": "max",
        },
        {
            "name": "mean_edge",
            "passed": (paper_payload["mean_edge"] or 0.0) >= min_mean_edge,
            "value": paper_payload["mean_edge"],
            "threshold": min_mean_edge,
            "direction": "min",
        },
    ]
    return {
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
    }
