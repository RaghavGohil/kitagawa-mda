"""
Stats API — aggregate metrics for the dashboard.
Server-side TTL cache to avoid repeated heavy COUNT queries.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.connection import get_db

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])

# Server-side cache (recompute at most once per 60 seconds)
_stats_cache: dict | None = None
_stats_cache_ts: float = 0.0
_STATS_TTL = 60  # seconds


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """
    Get dashboard aggregate statistics.
    Results are cached for 60 seconds to reduce DB load on page reload.
    """
    global _stats_cache, _stats_cache_ts
    now = time.time()
    if _stats_cache and (now - _stats_cache_ts) < _STATS_TTL:
        return _stats_cache

    # Active vessels (distinct MMSI in last 24h)
    vessels_result = await db.execute(
        text("SELECT COUNT(DISTINCT mmsi) FROM ais_tracks WHERE timestamp > NOW() - INTERVAL '24 hours'")
    )
    active_vessels = vessels_result.scalar() or 0
    
    # Anomalies: unidentified vessels with AIS coverage available
    anomalies_result = await db.execute(
        text("""
            SELECT COUNT(*) FROM detections d
            WHERE d.mmsi IS NULL
              AND EXISTS (
                  SELECT 1 FROM ais_coverage_dates c
                  WHERE c.date = DATE_TRUNC('day', d.detection_datetime)::date
                    AND c.has_coverage = 1
              )
        """)
    )
    anomalies_detected = anomalies_result.scalar() or 0
    
    # Unidentified (no AIS coverage)
    unidentified_result = await db.execute(
        text("""
            SELECT COUNT(*) FROM detections d
            WHERE d.mmsi IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM ais_coverage_dates c
                  WHERE c.date = DATE_TRUNC('day', d.detection_datetime)::date
                    AND c.has_coverage = 1
              )
        """)
    )
    unidentified_count = unidentified_result.scalar() or 0
    
    # Sensor counts
    sar_result = await db.execute(text("SELECT COUNT(*) FROM detections WHERE sensor_type = 'SAR'"))
    sar_detections = sar_result.scalar() or 0
    
    eo_result = await db.execute(text("SELECT COUNT(*) FROM detections WHERE sensor_type = 'EO'"))
    eo_detections = eo_result.scalar() or 0
    
    # Average speed from AIS
    speed_result = await db.execute(text("SELECT AVG(sog) FROM ais_tracks WHERE timestamp > NOW() - INTERVAL '1 hour'"))
    avg_speed = speed_result.scalar() or 0.0
    
    # Identified count
    identified_result = await db.execute(text("SELECT COUNT(DISTINCT mmsi) FROM detections WHERE mmsi IS NOT NULL AND mmsi > 0"))
    identified_count = identified_result.scalar() or 0

    result = {
        "active_vessels": active_vessels,
        "anomalies_detected": anomalies_detected,
        "unidentified_count": unidentified_count,
        "identified_count": identified_count,
        "sar_detections": sar_detections,
        "eo_detections": eo_detections,
        "average_speed": round(float(avg_speed), 2),
        "vessels_by_type": {
            "ship": identified_count,
            "unidentified": unidentified_count + anomalies_detected,
        }
    }

    _stats_cache = result
    _stats_cache_ts = now
    return result
