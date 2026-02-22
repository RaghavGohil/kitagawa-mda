"""
Vessels API — correlating detections with AIS identity data.

Provides vessel-centric views of detection data, grouping detections
by their correlated MMSI for a vessel-centric map view.
"""

from __future__ import annotations

import io
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend_server.db.connection import get_db

router = APIRouter(prefix="/api/v1/vessels", tags=["vessels"])


@router.get("")
async def get_vessels(
    min_lon: Optional[float] = Query(None),
    min_lat: Optional[float] = Query(None),
    max_lon: Optional[float] = Query(None),
    max_lat: Optional[float] = Query(None),
    zoom: int = Query(10, ge=1, le=22),
    anomaly_only: bool = Query(False),
    satellite_type: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
):
    """
    Get vessels (correlated detections).
    Optionally filter by bounding box, anomaly status, or sensor type.
    """
    where_clauses = []
    params = {"limit": limit}

    if min_lon is not None and min_lat is not None and max_lon is not None and max_lat is not None:
        where_clauses.append("ST_Intersects(geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))")
        params.update({"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat})

    if anomaly_only:
        where_clauses.append("(correlation_distance_m > 500 OR correlation_distance_m IS NULL)")

    if satellite_type:
        where_clauses.append("sensor_type = :sensor")
        params["sensor"] = satellite_type

    where_str = " AND ".join(where_clauses) if where_clauses else "TRUE"

    sql = text(f"""
        SELECT
            COALESCE(mmsi, -id) AS v_id,
            COUNT(*) AS detection_count,
            AVG(confidence) AS avg_confidence,
            MAX(detection_datetime) AS last_seen,
            AVG(ST_Y(geom)) AS lat,
            AVG(ST_X(geom)) AS lon,
            ARRAY_AGG(sensor_type) AS sensor_types,
            AVG(correlation_distance_m) AS avg_dist,
            MAX(custom_name) AS display_name,
            MAX(COALESCE(mmsi, 0)) as real_mmsi
        FROM detections
        WHERE {where_str}
        GROUP BY COALESCE(mmsi, -id)
        ORDER BY last_seen DESC
        LIMIT :limit
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    return {
        "vessels": [
            {
                "mmsi": r[9],  # Real MMSI (0 if uncorrelated)
                "v_id": r[0],  # Unique grouping ID
                "name": r[8] if r[8] else (f"Vessel {r[9]}" if r[9] != 0 else f"Unidentified {abs(r[0])}"),
                "detection_count": r[1],
                "avg_confidence": round(r[2], 4) if r[2] else None,
                "last_seen": r[3].isoformat() if r[3] else None,
                "lat": round(r[4], 6),
                "lon": round(r[5], 6),
                "sensor_types": list(set(r[6])) if r[6] else [],
                "anomaly_type": "none" if (r[7] is not None and r[7] <= 750) else "anomaly",
                "is_identified": r[9] > 0
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/chips/{detection_id}")
async def get_chip_image(
    detection_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Proxy endpoint to serve chip images from MinIO to the browser."""
    result = await db.execute(
        text("SELECT minio_key FROM image_chips WHERE detection_id = :det_id"),
        {"det_id": detection_id},
    )
    row = result.fetchone()
    if not row or not row[0]:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chip not found")

    from backend_server.services.chips import get_minio_client
    from shared.config import MINIO_BUCKET

    client = get_minio_client()
    try:
        response = client.get_object(MINIO_BUCKET, row[0])
        data = io.BytesIO(response.read())
        response.close()
        response.release_conn()
        return StreamingResponse(data, media_type="image/png")
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chip not found in storage")


@router.get("/{mmsi}")
async def get_vessel(
    mmsi: int,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information about a specific vessel."""
    is_unidentified = mmsi < 0
    where_clause = "d.id = :mmsi_val" if is_unidentified else "d.mmsi = :mmsi_val"
    mmsi_val = abs(mmsi) if is_unidentified else mmsi

    # All detections for this MMSI (or single detection if unidentified)
    det_result = await db.execute(
        text(f"""
            SELECT
                d.id, d.image_name, d.sensor_type, d.confidence,
                d.detection_datetime, d.correlation_distance_m,
                ST_Y(d.geom) AS lat, ST_X(d.geom) AS lon,
                ic.minio_key, d.custom_name
            FROM detections d
            LEFT JOIN image_chips ic ON ic.detection_id = d.id
            WHERE {where_clause}
            ORDER BY d.detection_datetime DESC
        """),
        {"mmsi_val": mmsi_val},
    )
    det_rows = det_result.fetchall()
    
    latest_dist = det_rows[0][5] if det_rows else None
    anomaly_type = "none" if (latest_dist is not None and latest_dist <= 750) else "anomaly"

    # Latest AIS track snippet
    ais_result = await db.execute(
        text("""
            SELECT
                timestamp, ST_Y(geom) AS lat, ST_X(geom) AS lon,
                COALESCE(sog, 0) AS sog, COALESCE(cog, 0) AS cog
            FROM ais_tracks
            WHERE mmsi = :mmsi
            ORDER BY timestamp DESC
            LIMIT 100
        """),
        {"mmsi": mmsi},
    )
    ais_rows = ais_result.fetchall()

    detections = []
    for r in det_rows:
        chip_url = ""
        if r[8]:
            # Use proxy URL so the browser can reach the image
            chip_url = f"/api/v1/vessels/chips/{r[0]}"
        detections.append({
            "id": r[0],
            "image_name": r[1],
            "sensor_type": r[2],
            "confidence": round(r[3], 4),
            "detection_datetime": r[4].isoformat() if r[4] else None,
            "correlation_distance_m": round(r[5], 2) if r[5] else None,
            "lat": round(r[6], 6),
            "lon": round(r[7], 6),
            "chip_url": chip_url,
        })

    track = [
        {
            "timestamp": p[0].isoformat() if p[0] else None,
            "lat": round(p[1], 6),
            "lon": round(p[2], 6),
            "sog": round(p[3], 2),
            "cog": round(p[4], 2),
        }
        for p in ais_rows
    ]

    return {
        "mmsi": mmsi_val if not is_unidentified else 0,
        "v_id": mmsi, # This is the unique grouping key
        "name": det_rows[0][9] if (det_rows and det_rows[0][9]) else (f"Vessel {mmsi_val}" if not is_unidentified else f"Unidentified {mmsi_val}"),
        "detection_count": len(detections),
        "anomaly_type": anomaly_type,
        "detections": detections,
        "recent_track": track,
    }
