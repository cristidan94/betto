from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationBucket:
    lower: float
    upper: float
    count: int
    mean_prediction: float | None
    observed_rate: float | None


def brier_score(predictions: list[float], targets: list[int]) -> float:
    _validate_predictions(predictions, targets)
    return sum((prediction - target) ** 2 for prediction, target in zip(predictions, targets, strict=True)) / len(predictions)


def log_loss(predictions: list[float], targets: list[int], eps: float = 1e-15) -> float:
    _validate_predictions(predictions, targets)
    total = 0.0
    for prediction, target in zip(predictions, targets, strict=True):
        clipped = min(max(prediction, eps), 1 - eps)
        total += target * math.log(clipped) + (1 - target) * math.log(1 - clipped)
    return -total / len(predictions)


def calibration_buckets(predictions: list[float], targets: list[int], bucket_count: int = 10) -> list[CalibrationBucket]:
    _validate_predictions(predictions, targets)
    if bucket_count <= 0:
        raise ValueError("bucket_count must be positive")
    rows: list[list[tuple[float, int]]] = [[] for _ in range(bucket_count)]
    for prediction, target in zip(predictions, targets, strict=True):
        index = min(bucket_count - 1, int(prediction * bucket_count))
        rows[index].append((prediction, target))
    buckets: list[CalibrationBucket] = []
    width = 1 / bucket_count
    for index, values in enumerate(rows):
        lower = index * width
        upper = 1.0 if index == bucket_count - 1 else (index + 1) * width
        if values:
            mean_prediction = sum(prediction for prediction, _ in values) / len(values)
            observed_rate = sum(target for _, target in values) / len(values)
        else:
            mean_prediction = None
            observed_rate = None
        buckets.append(CalibrationBucket(lower, upper, len(values), mean_prediction, observed_rate))
    return buckets


def expected_calibration_error(predictions: list[float], targets: list[int], bucket_count: int = 10) -> float:
    buckets = calibration_buckets(predictions, targets, bucket_count)
    total = len(predictions)
    return sum(
        (bucket.count / total) * abs((bucket.mean_prediction or 0.0) - (bucket.observed_rate or 0.0))
        for bucket in buckets
        if bucket.count > 0
    )


def _validate_predictions(predictions: list[float], targets: list[int]) -> None:
    if not predictions:
        raise ValueError("predictions cannot be empty")
    if len(predictions) != len(targets):
        raise ValueError("predictions and targets must have the same length")
    if any(not 0 <= prediction <= 1 for prediction in predictions):
        raise ValueError("predictions must be between 0 and 1")
    if any(target not in (0, 1) for target in targets):
        raise ValueError("targets must be binary")

