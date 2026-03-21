"""
Backend Server — FastAPI application.

Serves as the primary API for the frontend (Leaflet).
Handles data ingestion, AIS correlation, and detection queries.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.ais_tracks import router as ais_router
from backend.api.alerts import router as alerts_router
from backend.api.detections import router as detections_router
from backend.api.pipeline import (
    router as pipeline_router,
    start_background_ingest_polling,
)
from backend.api.stats import router as stats_router
from backend.api.vessels import router as vessels_router
from backend.api.boundaries import router as boundaries_router
from backend.api.ais_live import router as ais_live_router
from backend.db.connection import close_db, init_db


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    import socket

    try:
        print("[DEBUG] Resolving postgres:", socket.gethostbyname("postgres"))
    except Exception as e:
        print("[DEBUG] gethostbyname error:", e)
    print("[Backend Server] Initializing database...")
    await init_db()

    # Ensure local dev has boundaries if missing
    import os
    from backend.services.boundaries import ensure_local_boundaries

    await ensure_local_boundaries()

    if not os.getenv("DISABLE_AUTO_INGEST"):
        asyncio.create_task(start_background_ingest_polling())
    else:
        print("[Backend Server] Auto-ingest disabled via DISABLE_AUTO_INGEST flag.")

    # Start real-time AIS stream if API key is configured
    from shared.config import AISSTREAM_API_KEY, AISSTREAM_AUTO_START
    from backend.services import ais_stream

    if AISSTREAM_API_KEY and AISSTREAM_AUTO_START:
        ais_stream.start()
        print("[Backend Server] Live AIS stream started.")
    elif not AISSTREAM_API_KEY:
        print("[Backend Server] Live AIS disabled (AISSTREAM_API_KEY not set).")

    yield

    # Graceful shutdown
    ais_stream.stop()
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

# CORS for frontend (Permissive for localtunnel/vercel demonstration)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*", "bypass-tunnel-reminder"],
)

# Register routers
app.include_router(detections_router)
app.include_router(ais_router)
app.include_router(vessels_router)
app.include_router(pipeline_router)
app.include_router(alerts_router)
app.include_router(stats_router)
app.include_router(boundaries_router)
app.include_router(ais_live_router)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    from shared.utils import check_resources, get_free_disk_gb, get_memory_usage_mb
    import psutil
    import os

    ok, msg = check_resources(min_disk_gb=1.0)
    data_dir = os.getenv("DATA_DIR", "/data")

    return {
        "status": "healthy" if ok else "resource_constrained",
        "service": "backend-server",
        "resources": {
            "ok": ok,
            "message": msg,
            "free_disk_gb": round(
                get_free_disk_gb(data_dir if os.path.exists(data_dir) else "."), 2
            ),
            "memory_percent": psutil.virtual_memory().percent,
            "process_memory_mb": round(get_memory_usage_mb(), 2),
        },
    }
