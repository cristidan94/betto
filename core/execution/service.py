from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from core.edge import Recommendation
from core.markets import MarketSnapshot
from core.markets.probability import market_mid_probability


class BetMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    order_id: str
    mode: BetMode
    market_id: str
    outcome: str
    side: str
    size_usd: float
    fill_price: float | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "order_id": self.order_id,
            "mode": self.mode.value,
            "market_id": self.market_id,
            "outcome": self.outcome,
            "side": self.side,
            "size_usd": self.size_usd,
            "fill_price": self.fill_price,
            "error": self.error,
        }


class ExecutionService:
    """Unified bet execution for paper and live modes.

    In paper mode, simulates fills at the current mid-price.
    In live mode, delegates to a PolymarketOrderClient.
    """

    def __init__(
        self,
        mode: BetMode = BetMode.PAPER,
        order_client: Any | None = None,
        bankroll_usd: float = 1000.0,
        daily_cap_fraction: float = 0.20,
        max_single_bet_fraction: float = 0.04,
    ) -> None:
        self.mode = mode
        self.order_client = order_client
        self.bankroll_usd = bankroll_usd
        self.daily_cap_fraction = daily_cap_fraction
        self.max_single_bet_fraction = max_single_bet_fraction
        self._daily_placed_usd = 0.0

    def execute_recommendation(
        self,
        recommendation: Recommendation,
        snapshot: MarketSnapshot,
        token_id: str | None = None,
    ) -> ExecutionResult:
        if not recommendation.passes_filter:
            return ExecutionResult(
                success=False,
                order_id="",
                mode=self.mode,
                market_id=recommendation.market_id,
                outcome=recommendation.outcome,
                side="buy",
                size_usd=0.0,
                fill_price=None,
                error="recommendation does not pass filter",
            )

        size_usd = recommendation.bankroll_fraction * self.bankroll_usd
        size_usd = min(size_usd, self.max_single_bet_fraction * self.bankroll_usd)

        daily_remaining = (self.daily_cap_fraction * self.bankroll_usd) - self._daily_placed_usd
        if size_usd > daily_remaining:
            return ExecutionResult(
                success=False,
                order_id="",
                mode=self.mode,
                market_id=recommendation.market_id,
                outcome=recommendation.outcome,
                side="buy",
                size_usd=size_usd,
                fill_price=None,
                error=f"daily cap exceeded (remaining: ${daily_remaining:.2f})",
            )

        if self.mode == BetMode.PAPER:
            return self._execute_paper(recommendation, snapshot, size_usd)
        else:
            return self._execute_live(recommendation, snapshot, size_usd, token_id)

    def _execute_paper(
        self,
        recommendation: Recommendation,
        snapshot: MarketSnapshot,
        size_usd: float,
    ) -> ExecutionResult:
        try:
            fill_price = market_mid_probability(snapshot)
        except ValueError:
            fill_price = recommendation.market_prob

        order_id = f"paper-{uuid.uuid4().hex[:12]}"
        self._daily_placed_usd += size_usd

        return ExecutionResult(
            success=True,
            order_id=order_id,
            mode=BetMode.PAPER,
            market_id=recommendation.market_id,
            outcome=recommendation.outcome,
            side="buy",
            size_usd=size_usd,
            fill_price=fill_price,
            error=None,
        )

    def _execute_live(
        self,
        recommendation: Recommendation,
        snapshot: MarketSnapshot,
        size_usd: float,
        token_id: str | None,
    ) -> ExecutionResult:
        if self.order_client is None:
            return ExecutionResult(
                success=False,
                order_id="",
                mode=BetMode.LIVE,
                market_id=recommendation.market_id,
                outcome=recommendation.outcome,
                side="buy",
                size_usd=size_usd,
                fill_price=None,
                error="no order client configured — set Polymarket credentials",
            )

        if not token_id:
            return ExecutionResult(
                success=False,
                order_id="",
                mode=BetMode.LIVE,
                market_id=recommendation.market_id,
                outcome=recommendation.outcome,
                side="buy",
                size_usd=size_usd,
                fill_price=None,
                error="token_id required for live orders",
            )

        result = self.order_client.place_market_order(
            token_id=token_id,
            side="BUY",
            size=size_usd,
        )

        if not result.success:
            return ExecutionResult(
                success=False,
                order_id="",
                mode=BetMode.LIVE,
                market_id=recommendation.market_id,
                outcome=recommendation.outcome,
                side="buy",
                size_usd=size_usd,
                fill_price=None,
                error=result.error,
            )

        self._daily_placed_usd += size_usd
        return ExecutionResult(
            success=True,
            order_id=result.order.order_id if result.order else "",
            mode=BetMode.LIVE,
            market_id=recommendation.market_id,
            outcome=recommendation.outcome,
            side="buy",
            size_usd=size_usd,
            fill_price=result.order.price if result.order else None,
            error=None,
        )
