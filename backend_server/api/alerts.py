"""
Alerts API — providing notifications for anomalous vessel behavior.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend_server.db.connection import get_db

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

@router.get("")
async def get_alerts(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get recent anomaly alerts.
    Currently defines alerts as detections with a high correlation distance
    or other anomalous indicators.
    """
    # Simple alert logic: detections with correlation distance > 500m
    # or just recent detections that were correlated.
    # Frontend expects: { alerts: { id, vessel_id, vessel_name, type, timestamp } }
    
    result = await db.execute(
        text("""
            SELECT 
                d.id, 
                d.mmsi, 
                d.image_name, 
                d.detection_datetime,
                d.correlation_distance_m
            FROM detections d
            WHERE d.mmsi IS NOT NULL
              AND (d.correlation_distance_m > 500 OR d.correlation_distance_m IS NULL)
            ORDER BY d.detection_datetime DESC
            LIMIT :limit
        """),
        {"limit": limit}
    )
    rows = result.fetchall()
    
    alerts = []
    for r in rows:
        alerts.append({
            "id": f"alert-{r[0]}",
            "vessel_id": str(r[1]),
            "vessel_name": f"Vessel {r[1]}", # We don't have names in DB yet, so use MMSI
            "type": "anomaly",
            "timestamp": r[3].isoformat() if r[3] else None,
        })
        
    return {
        "alerts": alerts,
        "total": len(alerts)
    }
