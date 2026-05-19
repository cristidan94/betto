from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from core.backtesting import WalkForwardWindow, build_walk_forward_windows
from core.modeling import brier_score, expected_calibration_error, log_loss
from sports.cs.models.baseline import BaselineMapWinnerModel
from sports.cs.models.dataset import build_map_winner_dataset
from sports.cs.normalization.records import CsParsedMatch


@dataclass(frozen=True)
class WalkForwardEvaluation:
    window: WalkForwardWindow
    rows: int
    metrics: dict[str, float]


def evaluate_baseline_walk_forward(
    matches: list[CsParsedMatch],
    start: date,
    end: date,
    train_days: int,
    validate_days: int,
    step_days: int,
) -> list[WalkForwardEvaluation]:
    windows = build_walk_forward_windows(start, end, train_days, validate_days, step_days)
    all_rows = build_map_winner_dataset(matches)
    model = BaselineMapWinnerModel()
    results: list[WalkForwardEvaluation] = []
    for window in windows:
        validation_rows = [
            row
            for row in all_rows
            if window.validate_start <= row.as_of.date() <= window.validate_end
        ]
        if not validation_rows:
            continue
        predictions = model.predict(validation_rows)
        targets = [row.target for row in validation_rows]
        results.append(
            WalkForwardEvaluation(
                window=window,
                rows=len(validation_rows),
                metrics={
                    "brier_score": brier_score(predictions, targets),
                    "log_loss": log_loss(predictions, targets),
                    "expected_calibration_error": expected_calibration_error(predictions, targets),
                },
            )
        )
    return results


def walk_forward_payload(results: list[WalkForwardEvaluation]) -> list[dict[str, object]]:
    return [
        {
            "window": {key: value.isoformat() for key, value in asdict(result.window).items()},
            "rows": result.rows,
            "metrics": result.metrics,
        }
        for result in results
    ]


def summarize_walk_forward_results(results: list[WalkForwardEvaluation]) -> dict[str, float | int | None]:
    total_rows = sum(result.rows for result in results)
    if total_rows == 0:
        return {
            "windows": len(results),
            "rows": 0,
            "brier_score": None,
            "log_loss": None,
            "expected_calibration_error": None,
        }
    return {
        "windows": len(results),
        "rows": total_rows,
        "brier_score": _weighted_metric(results, "brier_score", total_rows),
        "log_loss": _weighted_metric(results, "log_loss", total_rows),
        "expected_calibration_error": _weighted_metric(results, "expected_calibration_error", total_rows),
    }


def _weighted_metric(results: list[WalkForwardEvaluation], metric_name: str, total_rows: int) -> float:
    return sum(result.metrics[metric_name] * result.rows for result in results) / total_rows
