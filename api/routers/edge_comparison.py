from fastapi import APIRouter

from api.data import get_edge_comparison as read_edge_comparison
from api.models.edge_comparison import EdgeComparisonResponse

router = APIRouter()


@router.get("/edge-comparison", response_model=EdgeComparisonResponse)
async def get_edge_comparison() -> EdgeComparisonResponse:
    return read_edge_comparison()
