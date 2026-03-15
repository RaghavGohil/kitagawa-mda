"""
API endpoints for controlling the live AIS stream.

Routes:
  GET  /ais/live/status  — connection state, message count, etc.
  POST /ais/live/start   — start the WebSocket listener
  POST /ais/live/stop    — stop the WebSocket listener
"""

from __future__ import annotations

from fastapi import APIRouter

from backend_server.services.ais_stream import get_status, start, stop

router = APIRouter(prefix="/ais/live", tags=["AIS Live"])


@router.get("/status")
async def live_status():
    """Current status of the live AIS WebSocket stream."""
    return get_status()


@router.post("/start")
async def live_start():
    """Start receiving real-time AIS data from aisstream.io."""
    return start()


@router.post("/stop")
async def live_stop():
    """Stop the real-time AIS data stream."""
    return stop()
