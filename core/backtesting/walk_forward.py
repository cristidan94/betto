from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: date
    train_end: date
    validate_start: date
    validate_end: date


def build_walk_forward_windows(
    start: date,
    end: date,
    train_days: int,
    validate_days: int,
    step_days: int,
) -> list[WalkForwardWindow]:
    if train_days <= 0 or validate_days <= 0 or step_days <= 0:
        raise ValueError("window sizes must be positive")
    windows: list[WalkForwardWindow] = []
    train_start = start
    while True:
        train_end = train_start + timedelta(days=train_days)
        validate_start = train_end + timedelta(days=1)
        validate_end = validate_start + timedelta(days=validate_days - 1)
        if validate_end > end:
            break
        windows.append(WalkForwardWindow(train_start, train_end, validate_start, validate_end))
        train_start = train_start + timedelta(days=step_days)
    return windows

