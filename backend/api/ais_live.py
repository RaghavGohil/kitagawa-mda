import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.services.ais_stream import (
    get_status,
    start,
    stop,
    subscribe,
    unsubscribe,
    set_active_bboxes,
)

router = APIRouter(prefix="/api/v1/ais/live", tags=["ais_live"])


@router.get("/status")
async def live_status():
    """Current status of the live AIS WebSocket stream."""
    return get_status()


@router.post("/start")
async def start_stream():
    """Start receiving real-time AIS data from aisstream.io."""
    return start()


@router.post("/stop")
async def stop_stream():
    """Stop the real-time AIS data stream."""
    return stop()


@router.get("/positions")
async def get_live_positions(
    min_lon: Optional[float] = Query(None),
    min_lat: Optional[float] = Query(None),
    max_lon: Optional[float] = Query(None),
    max_lat: Optional[float] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Get latest known positions for all active vessels in the stream.
    Optional bounding box filtering.
    """
    where_clause = ""
    params = {}
    if all(v is not None for v in [min_lon, min_lat, max_lon, max_lat]):
        where_clause = (
            "AND geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)"
        )
        params = {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
        }

    # Only return vessels seen in the last 30 minutes
    sql = f"""
        SELECT DISTINCT ON (mmsi)
            mmsi, timestamp, sog, cog, 
            ST_X(geom) as lon, ST_Y(geom) as lat
        FROM ais_tracks
        WHERE timestamp > NOW() - INTERVAL '30 minutes'
        {where_clause}
        ORDER BY mmsi, timestamp DESC
    """
    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    return [
        {
            "mmsi": r[0],
            "timestamp": r[1].isoformat(),
            "sog": float(r[2] or 0),
            "cog": float(r[3] or 0),
            "lon": float(r[4]),
            "lat": float(r[5]),
        }
        for r in rows
    ]


@router.websocket("/ws")
async def live_ais_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time AIS updates.
    Supports dynamic AOI subscription messages:
    { "type": "subscribe", "bbox": [[[min_lat, min_lon], [max_lat, max_lon]]] }
    """
    await websocket.accept()
    queue = subscribe()

    async def listener():
        try:
            while True:
                msg = await queue.get()
                await websocket.send_json(msg)
        except Exception:
            pass

    listener_task = asyncio.create_task(listener())

    try:
        while True:
            # Check for incoming subscription updates from the client
            try:
                data = await websocket.receive_json()
                if data.get("type") == "subscribe":
                    bbox = data.get("bbox")
                    if bbox:
                        await set_active_bboxes(bbox)
            except Exception:
                # Handle non-JSON or other message errors gracefully
                await asyncio.sleep(0.1)

    except (WebSocketDisconnect, Exception):
        pass
    finally:
        unsubscribe(queue)
        listener_task.cancel()
