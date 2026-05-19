from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import betlog, ingestion, matches, recommendation, risk, strategy, today

app = FastAPI(title="betto API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(today.router, prefix="/api")
app.include_router(recommendation.router, prefix="/api")
app.include_router(matches.router, prefix="/api")
app.include_router(strategy.router, prefix="/api")
app.include_router(betlog.router, prefix="/api")
app.include_router(ingestion.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
