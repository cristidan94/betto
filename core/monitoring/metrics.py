from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MetricEvent:
    name: str
    value: float
    observed_at: datetime
    tags: dict[str, str]

