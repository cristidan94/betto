from __future__ import annotations

from fastapi import APIRouter

from api.data import get_bet_log as read_bet_log
from api.models.betlog import BetLogResponse

router = APIRouter()


@router.get("/bets", response_model=BetLogResponse)
async def get_bet_log() -> BetLogResponse:
    return read_bet_log()
