from __future__ import annotations

import random
import time
from datetime import datetime, timezone


class RateLimiter:
    def __init__(
        self,
        min_delay: int = 8,
        max_delay: int = 15,
        cooldown_every: int = 50,
        cooldown_seconds: int = 120,
        daily_cap: int = 5000,
        quiet_hours_start: int = 3,
        quiet_hours_end: int = 6,
        initial_request_count: int = 0,
    ) -> None:
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.cooldown_every = cooldown_every
        self.cooldown_seconds = cooldown_seconds
        self.daily_cap = daily_cap
        self.quiet_hours_start = quiet_hours_start
        self.quiet_hours_end = quiet_hours_end
        self.request_count = initial_request_count
        self.failure_count = 0

    def next_delay(self) -> float:
        next_count = self.request_count + 1
        if self.cooldown_every and next_count % self.cooldown_every == 0:
            return float(self.cooldown_seconds)
        return random.uniform(self.min_delay, self.max_delay)

    def sleep(self) -> None:
        time.sleep(self.next_delay())

    def record_success(self) -> None:
        self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1

    def record_request(self) -> None:
        self.request_count += 1

    def failure_backoff_delay(self) -> float:
        if self.failure_count <= 0:
            return 0.0
        return min(900.0, float(2 ** min(self.failure_count, 8)))

    def daily_cap_reached(self) -> bool:
        return self.request_count >= self.daily_cap

    def in_quiet_hours(self) -> bool:
        hour = _utcnow_hour()
        if self.quiet_hours_start <= self.quiet_hours_end:
            return self.quiet_hours_start <= hour < self.quiet_hours_end
        return hour >= self.quiet_hours_start or hour < self.quiet_hours_end


def _utcnow_hour() -> int:
    return datetime.now(timezone.utc).hour
