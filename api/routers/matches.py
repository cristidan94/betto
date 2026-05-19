from __future__ import annotations

from fastapi import APIRouter

from api.data import get_matches as read_matches
from api.data import get_match_markets as read_match_markets
from api.models.matches import MatchesResponse, MatchMarketsResponse

router = APIRouter()


@router.get("/matches", response_model=MatchesResponse)
async def get_matches() -> MatchesResponse:
    return read_matches()


@router.get("/matches/{match_id}/markets", response_model=MatchMarketsResponse)
async def get_match_markets(match_id: str) -> MatchMarketsResponse:
    return read_match_markets(match_id)
