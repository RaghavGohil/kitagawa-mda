"""
Stats API — aggregate metrics for the dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend_server.db.connection import get_db

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])

@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """
    Get dashboard aggregate statistics.
    """
    # Active vessels (distinct MMSI in last 24h)
    vessels_result = await db.execute(
        text("SELECT COUNT(DISTINCT mmsi) FROM ais_tracks WHERE timestamp > NOW() - INTERVAL '24 hours'")
    )
    active_vessels = vessels_result.scalar() or 0
    
    # Anomalies detected (correlated detections with high distance or no MMSI)
    # For now, let's just count all detections in last 24h as a placeholder for "activity"
    # or specific ones.
    anomalies_result = await db.execute(
        text("SELECT COUNT(*) FROM detections WHERE mmsi IS NOT NULL AND (correlation_distance_m > 500 OR correlation_distance_m IS NULL)")
    )
    anomalies_detected = anomalies_result.scalar() or 0
    
    # Sensor counts
    sar_result = await db.execute(text("SELECT COUNT(*) FROM detections WHERE sensor_type = 'SAR'"))
    sar_detections = sar_result.scalar() or 0
    
    eo_result = await db.execute(text("SELECT COUNT(*) FROM detections WHERE sensor_type = 'EO'"))
    eo_detections = eo_result.scalar() or 0
    
    # Average speed from AIS
    speed_result = await db.execute(text("SELECT AVG(sog) FROM ais_tracks WHERE timestamp > NOW() - INTERVAL '1 hour'"))
    avg_speed = speed_result.scalar() or 0.0
    
    return {
        "active_vessels": active_vessels,
        "anomalies_detected": anomalies_detected,
        "sar_detections": sar_detections,
        "eo_detections": eo_detections,
        "average_speed": round(float(avg_speed), 2),
        "vessels_by_type": {"ship": active_vessels}
    }
