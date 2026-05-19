from fastapi import APIRouter

from api.data import get_today_recommendations as read_today_recommendations
from api.models.today import TodayResponse

router = APIRouter()


@router.get("/today/recommendations", response_model=TodayResponse)
async def get_today_recommendations() -> TodayResponse:
    return read_today_recommendations()
