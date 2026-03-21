"""
Alerts API — providing notifications for anomalous vessel behavior.

Two alert types:
  - 'anomaly':      Correlated vessels with high correlation distance (> 500m)
  - 'unidentified': Unidentified vessels detected when AIS data WAS available
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.connection import get_db

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

@router.get("")
async def get_alerts(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get recent alerts:
      1. Anomaly alerts: identified vessels with correlation_distance > 500m
      2. Unidentified alerts: unmatched detections where AIS data was available
    """
    # 1. Correlation distance anomalies (identified but far from AIS position)
    corr_result = await db.execute(
        text("""
            SELECT 
                d.id, 
                d.mmsi, 
                d.custom_name,
                d.detection_datetime,
                d.correlation_distance_m,
                'anomaly' as alert_type
            FROM detections d
            WHERE d.mmsi IS NOT NULL 
              AND d.mmsi > 0
              AND d.correlation_distance_m > 500
            ORDER BY d.detection_datetime DESC
            LIMIT :limit
        """),
        {"limit": limit}
    )
    corr_rows = corr_result.fetchall()
    
    # 2. Unidentified vessels in AIS-covered areas (genuinely suspicious)
    unid_result = await db.execute(
        text("""
            SELECT 
                d.id,
                0 as mmsi,
                d.custom_name,
                d.detection_datetime,
                NULL as correlation_distance_m,
                'unidentified_in_coverage' as alert_type
            FROM detections d
            WHERE d.mmsi IS NULL
              AND d.detection_datetime IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM ais_coverage_dates c
                  WHERE c.date = DATE_TRUNC('day', d.detection_datetime)::date
                    AND c.has_coverage = 1
              )
            ORDER BY d.detection_datetime DESC
            LIMIT :limit
        """),
        {"limit": limit}
    )
    unid_rows = unid_result.fetchall()
    
    # Merge and sort by datetime descending
    all_rows = list(corr_rows) + list(unid_rows)
    all_rows.sort(key=lambda r: r[3] if r[3] else "", reverse=True)
    all_rows = all_rows[:limit]
    
    alerts = []
    for r in all_rows:
        mmsi = r[1]
        custom_name = r[2]
        alert_type = r[5]
        
        if alert_type == "anomaly":
            vessel_id = str(mmsi)
            vessel_name = custom_name if custom_name else f"Vessel {mmsi}"
        else:
            vessel_id = f"unidentified-{r[0]}"
            vessel_name = custom_name if custom_name else f"Unidentified {r[0]}"
        
        alerts.append({
            "id": f"alert-{r[0]}",
            "vessel_id": vessel_id,
            "vessel_name": vessel_name,
            "type": alert_type,
            "timestamp": r[3].isoformat() if r[3] else None,
        })
        
    return {
        "alerts": alerts,
        "total": len(alerts)
    }
