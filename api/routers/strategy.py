from __future__ import annotations

from fastapi import APIRouter

from api.data import get_strategy as read_strategy
from api.models.strategy import StrategyResponse

router = APIRouter()


@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: str) -> StrategyResponse:
    return read_strategy(strategy_id)
