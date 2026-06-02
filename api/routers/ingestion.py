from __future__ import annotations

from fastapi import APIRouter

from api.data import get_ingestion as read_ingestion
from api.data import run_ingestion_job
from api.models.ingestion import IngestionJobRequest, IngestionJobResponse, IngestionResponse

router = APIRouter()


@router.get("/ingestion", response_model=IngestionResponse)
async def get_ingestion() -> IngestionResponse:
    return read_ingestion()


@router.post("/ingestion/jobs", response_model=IngestionJobResponse)
async def post_ingestion_job(req: IngestionJobRequest) -> IngestionJobResponse:
    return run_ingestion_job(req)
