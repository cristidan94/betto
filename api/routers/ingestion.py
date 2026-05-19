from __future__ import annotations

from fastapi import APIRouter

from api.data import get_ingestion as read_ingestion
from api.models.ingestion import IngestionResponse

router = APIRouter()


@router.get("/ingestion", response_model=IngestionResponse)
async def get_ingestion() -> IngestionResponse:
    return read_ingestion()
