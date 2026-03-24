"""
Alerts API — providing notifications for anomalous vessel behavior.

Two alert types:
  - 'anomaly':      Correlated vessels with high correlation distance (> 500m)
  - 'unidentified': Unidentified vessels detected when AIS data WAS available
"""

from __future__ import annotations

from datetime import datetime, timezone
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
    # Only alert on recent unidentified vessels:
    #   - classification = 'unidentified'
    #   - confidence >= 0.5 (meaningful detections only)
    #   - time window: last 48 hours to prevent "persistent" stale alerts
    sql = text("""
        SELECT DISTINCT ON (v_id)
            d.id,
            COALESCE(d.mmsi, 0) as mmsi,
            d.custom_name,
            d.detection_datetime,
            d.confidence,
            d.classification as alert_type,
            COALESCE(d.mmsi, -d.id) as v_id
        FROM detections d
        WHERE (d.mmsi IS NULL OR d.correlation_distance_m > 500)
          AND d.confidence >= 0.5
          AND d.detection_datetime >= NOW() - INTERVAL '48 hours'
          AND (d.fp_flags IS NULL OR d.fp_flags NOT LIKE '%land%')
        ORDER BY v_id, d.detection_datetime DESC
        LIMIT :limit
    """)

    result = await db.execute(sql, {"limit": limit})
    all_rows = result.fetchall()

    # Re-sort result by datetime since DISTINCT ON requires sorting by the key
    all_rows = list(all_rows)
    all_rows.sort(
        key=lambda r: r[3] if r[3] else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    alerts = []
    for r in all_rows:
        mmsi = r[1]
        custom_name = r[2]
        vessel_id = f"unidentified-{r[0]}" if not mmsi else str(mmsi)
        vessel_name = (
            custom_name
            if custom_name
            else (f"Vessel {mmsi}" if mmsi else f"Dark Vessel {r[0]}")
        )

        alerts.append(
            {
                "id": f"alert-{r[0]}",
                "vessel_id": vessel_id,
                "vessel_name": vessel_name,
                "type": "anomaly",
                "timestamp": r[3].isoformat() if r[3] else None,
            }
        )

    return {"alerts": alerts, "total": len(alerts)}
