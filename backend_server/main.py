"""
Backend Server — FastAPI application.

Serves as the primary API for the frontend (Leaflet).
Handles data ingestion, AIS correlation, and detection queries.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend_server.api.ais_tracks import router as ais_router
from backend_server.api.alerts import router as alerts_router
from backend_server.api.detections import router as detections_router
from backend_server.api.pipeline import router as pipeline_router, start_background_ingest_polling
from backend_server.api.stats import router as stats_router
from backend_server.api.vessels import router as vessels_router
from backend_server.db.connection import close_db, init_db


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Backend Server] Initializing database...")
    await init_db()
    print("[Backend Server] Database ready.")
    
    import asyncio
    asyncio.create_task(start_background_ingest_polling())
    
    yield
    await close_db()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Kitagawa Backend Server",
    description="Maritime surveillance backend — detections, AIS tracks, and vessel data",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(detections_router)
app.include_router(ais_router)
app.include_router(vessels_router)
app.include_router(pipeline_router)
app.include_router(alerts_router)
app.include_router(stats_router)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "backend-server"}
