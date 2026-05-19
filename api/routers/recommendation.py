from __future__ import annotations

from fastapi import APIRouter

from api.data import get_recommendation as read_recommendation
from api.models.recommendation import RecommendationDetail

router = APIRouter()


@router.get("/recommendations/{rec_id}", response_model=RecommendationDetail)
async def get_recommendation(rec_id: str) -> RecommendationDetail:
    return read_recommendation(rec_id)
