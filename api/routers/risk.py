from __future__ import annotations

from fastapi import APIRouter

from api.data import get_risk as read_risk
from api.models.risk import RiskResponse

router = APIRouter()


@router.get("/risk", response_model=RiskResponse)
async def get_risk() -> RiskResponse:
    return read_risk()
