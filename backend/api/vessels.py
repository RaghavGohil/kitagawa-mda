"""
Vessels API — correlating detections with AIS identity data.

Provides vessel-centric views of detection data, grouping detections
by their correlated MMSI for a vessel-centric map view.

4-State Classification:
  - identified:   Matched to AIS vessel (has MMSI)
  - no_anomaly:   Matched to AIS, correlation_distance <= 500m
  - anomaly:      Unidentified, but AIS data WAS available → suspicious
  - unidentified: Unidentified, and AIS data was NOT available → unknown
"""

from __future__ import annotations

import io
import math
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db


def _safe_round(val, ndigits):
    if val is None:
        return None
    try:
        f_val = float(val)
        if math.isnan(f_val) or math.isinf(f_val):
            return None
        return round(f_val, ndigits)
    except (ValueError, TypeError):
        return None


router = APIRouter(prefix="/api/v1/vessels", tags=["vessels"])

# ---------------------------------------------------------------------------
# AIS Coverage Cache (TTL-based, avoids per-request DB hits)
# ---------------------------------------------------------------------------
_ais_coverage_cache: dict[str, bool] = {}  # date_str -> has_coverage
_ais_coverage_cache_ts: float = 0.0
_AIS_COVERAGE_TTL = 300  # 5 minutes


async def _get_ais_coverage_dates(db: AsyncSession) -> dict[str, bool]:
    """Return a dict of date_str -> has_coverage, cached for 5 minutes."""
    global _ais_coverage_cache, _ais_coverage_cache_ts
    now = time.time()
    if _ais_coverage_cache and (now - _ais_coverage_cache_ts) < _AIS_COVERAGE_TTL:
        return _ais_coverage_cache

    result = await db.execute(text("SELECT date, has_coverage FROM ais_coverage_dates"))
    rows = result.fetchall()
    cache = {}
    for r in rows:
        date_key = r[0].strftime("%Y-%m-%d") if hasattr(r[0], "strftime") else str(r[0])
        cache[date_key] = bool(r[1])
    _ais_coverage_cache = cache
    _ais_coverage_cache_ts = now
    return cache


# ---------------------------------------------------------------------------
# Backend-authoritative classification color map
# ---------------------------------------------------------------------------
_CLASSIFICATION_COLORS = {
    "identified": "#10b981",  # Emerald green
    "anomaly": "#ef4444",  # Red — dark vessel (in coverage, no AIS)
    "out_of_coverage": "#6b7280",  # Gray — no AIS data available
}
_CLASSIFICATION_LABELS = {
    "identified": "Identified",
    "anomaly": "Dark Vessel",
    "out_of_coverage": "Out of Coverage",
}


def _classify_vessel(
    mmsi: int,
    correlation_dist: float | None,
    detection_date: str | None,
    coverage: dict[str, bool],
    db_classification: str | None = None,
) -> str:
    """
    3-State classification (fallback when db_classification is missing):
      - identified:      Matched AIS within 500m
      - anomaly:         In coverage area, no AIS match (dark vessel)
      - out_of_coverage: No AIS data for that area/date
    """
    if db_classification and db_classification in _CLASSIFICATION_COLORS:
        return db_classification

    if mmsi and mmsi > 0 and correlation_dist is not None and correlation_dist <= 200:
        return "identified"

    # Unidentified or bad match — check AIS coverage
    if detection_date:
        date_key = detection_date[:10]  # "YYYY-MM-DD"
        if coverage.get(date_key, False):
            return "anomaly"  # Coverage existed, vessel was dark

    return "out_of_coverage"


@router.get("")
async def get_vessels(
    min_lon: Optional[float] = Query(None),
    min_lat: Optional[float] = Query(None),
    max_lon: Optional[float] = Query(None),
    max_lat: Optional[float] = Query(None),
    zoom: int = Query(10, ge=1, le=22),
    anomaly_only: bool = Query(False),
    satellite_type: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=20000),
    db: AsyncSession = Depends(get_db),
):
    """
    Get vessels (correlated detections).
    Optionally filter by bounding box, anomaly status, or sensor type.
    """
    # Preload AIS coverage dates (cached)
    coverage = await _get_ais_coverage_dates(db)

    where_clauses = []
    params = {"limit": limit}

    if (
        min_lon is not None
        and min_lat is not None
        and max_lon is not None
        and max_lat is not None
    ):
        where_clauses.append(
            "ST_Intersects(geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))"
        )
        params.update(
            {
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            }
        )

    if anomaly_only:
        where_clauses.append(
            "(correlation_distance_m > 500 OR correlation_distance_m IS NULL)"
        )

    if satellite_type:
        where_clauses.append("sensor_type = :sensor")
        params["sensor"] = satellite_type

    where_str = " AND ".join(where_clauses) if where_clauses else "TRUE"

    # Landmask filter: exclude detections flagged as being on land
    landmask_filter = "(fp_flags IS NULL OR fp_flags NOT LIKE '%land%')"

    # Dynamic grid size for grouping based on zoom
    # z >= 15: ~1m (effectively no grouping)
    # z >= 8: ~10m
    # z < 8: ~50m
    grid_size = 0.00001 if zoom >= 15 else 0.0001 if zoom >= 8 else 0.0005

    # Simplified query — leverages stored classification
    sql = text(f"""
        SELECT
            COALESCE(mmsi, -MIN(id)) AS v_id,
            COUNT(*) AS detection_count,
            AVG(confidence) AS avg_confidence,
            MAX(detection_datetime) AS last_seen,
            AVG(ST_Y(geom)) AS lat,
            AVG(ST_X(geom)) AS lon,
            ARRAY_AGG(sensor_type) AS sensor_types,
            AVG(correlation_distance_m) AS avg_dist,
            MAX(custom_name) AS display_name,
            MAX(COALESCE(mmsi, 0)) as real_mmsi,
            MAX(classification) as global_classification
        FROM detections
        WHERE {where_str} AND {landmask_filter}
        GROUP BY
            mmsi,
            CASE WHEN mmsi IS NULL THEN ST_SnapToGrid(geom, :grid_size) ELSE NULL END
        ORDER BY last_seen DESC
        LIMIT :limit
    """)
    params["grid_size"] = grid_size

    result = await db.execute(sql, params)
    rows = result.fetchall()

    # Batch-fetch SOG/COG for identified vessels
    identified_mmsis = [int(r[9]) for r in rows if r[9] and int(r[9]) > 0]
    ais_info = {}
    if identified_mmsis:
        ais_result = await db.execute(
            text("""
                SELECT DISTINCT ON (mmsi) mmsi, sog, cog
                FROM ais_tracks
                WHERE mmsi = ANY(:mmsis)
                ORDER BY mmsi, timestamp DESC
            """),
            {"mmsis": identified_mmsis},
        )
        for ar in ais_result.fetchall():
            ais_info[int(ar[0])] = {"sog": ar[1], "cog": ar[2]}

    vessels = []
    for r in rows:
        real_mmsi = int(r[9]) if r[9] else 0
        last_seen_str = r[3].isoformat() if r[3] else None
        avg_dist = float(r[7]) if r[7] is not None else None
        db_cls = r[10]

        anomaly_type = _classify_vessel(
            real_mmsi, avg_dist, last_seen_str, coverage, db_classification=db_cls
        )
        color = _CLASSIFICATION_COLORS.get(anomaly_type, "#6b7280")
        ais = ais_info.get(real_mmsi, {})

        vessels.append(
            {
                "mmsi": real_mmsi,
                "v_id": r[0],
                "name": r[8]
                if r[8]
                else (
                    f"Vessel {real_mmsi}"
                    if real_mmsi > 0
                    else f"Unidentified {abs(r[0])}"
                ),
                "detection_count": r[1],
                "avg_confidence": _safe_round(r[2], 4),
                "last_seen": last_seen_str,
                "lat": _safe_round(r[4], 6),
                "lon": _safe_round(r[5], 6),
                "sensor_types": list(set(r[6])) if r[6] else [],
                "anomaly_type": anomaly_type,
                "color": color,
                "is_identified": real_mmsi > 0 and anomaly_type == "identified",
                "sog": _safe_round(ais.get("sog"), 2),
                "cog": _safe_round(ais.get("cog"), 2),
            }
        )

    return {
        "vessels": vessels,
        "total": len(vessels),
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

    from backend.services.chips import get_minio_client
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
    coverage = await _get_ais_coverage_dates(db)

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
                ic.minio_key, d.custom_name, d.classification
            FROM detections d
            LEFT JOIN image_chips ic ON ic.detection_id = d.id
            WHERE {where_clause}
            ORDER BY d.detection_datetime DESC
        """),
        {"mmsi_val": mmsi_val},
    )
    det_rows = det_result.fetchall()

    # Classify using detection date
    det_datetime_str = (
        det_rows[0][4].isoformat() if (det_rows and det_rows[0][4]) else None
    )
    avg_dist = det_rows[0][5] if det_rows else None
    db_cls = det_rows[0][10] if (det_rows and len(det_rows[0]) > 10) else None

    anomaly_type = _classify_vessel(
        0 if is_unidentified else mmsi_val,
        avg_dist,
        det_datetime_str,
        coverage,
        db_classification=db_cls,
    )

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
        detections.append(
            {
                "id": r[0],
                "image_name": r[1],
                "sensor_type": r[2],
                "confidence": _safe_round(r[3], 4),
                "detection_datetime": r[4].isoformat() if r[4] else None,
                "correlation_distance_m": _safe_round(r[5], 2),
                "lat": _safe_round(r[6], 6),
                "lon": _safe_round(r[7], 6),
                "chip_url": chip_url,
            }
        )

    track = [
        {
            "timestamp": p[0].isoformat() if p[0] else None,
            "lat": _safe_round(p[1], 6),
            "lon": _safe_round(p[2], 6),
            "sog": _safe_round(p[3], 2),
            "cog": _safe_round(p[4], 2),
        }
        for p in ais_rows
    ]

    return {
        "mmsi": mmsi_val if not is_unidentified else 0,
        "v_id": mmsi,  # This is the unique grouping key
        "name": det_rows[0][9]
        if (det_rows and det_rows[0][9])
        else (
            f"Vessel {mmsi_val}" if not is_unidentified else f"Unidentified {mmsi_val}"
        ),
        "detection_count": len(detections),
        "anomaly_type": anomaly_type,
        "detections": detections,
        "recent_track": track,
    }
