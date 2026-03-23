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

    try:
        result = await db.execute(
            text("SELECT date, has_coverage FROM ais_coverage_dates")
        )
        rows = result.fetchall()
        cache = {}
        for r in rows:
            date_key = (
                r[0].strftime("%Y-%m-%d") if hasattr(r[0], "strftime") else str(r[0])
            )
            cache[date_key] = bool(r[1])
        _ais_coverage_cache = cache
        _ais_coverage_cache_ts = now
        return cache
    except Exception as e:
        # Fallback if table doesn't exist yet or is inaccessible
        print(f"[Vessels] Failed to fetch AIS coverage: {e}")
        return {}


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
    zoom: float = Query(10, ge=1, le=22),
    anomaly_only: bool = Query(False),
    satellite_type: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=20000),
    db: AsyncSession = Depends(get_db),
):
    zoom = int(zoom)
    """
    Get vessels (correlated detections).
    Optionally filter by bounding box, anomaly status, or sensor type.
    """
    try:
        # Preload AIS coverage dates (cached)
        coverage = await _get_ais_coverage_dates(db)

        # Dynamic point limits for high-fidelity discovery
        # ... logic if needed ...
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
        # z >= 6: ~10m
        # z < 6: ~50m
        # Grid-based sampling for "Representative Ships" at low zoom
        # This prevents UI lag by picking 1 real high-confidence vessel per grid cell
        grid_size = 0.001  # Default small value for query stability
        representative_sql = ""
        vessel_order_sql = "ORDER BY last_seen DESC"

        # Increase grid size for more aggressive sparsification at low zoom (< 6)
        if zoom < 6:
            grid_size = 180.0 / (2**zoom)  # Larger cells for sparse display
            representative_sql = f"DISTINCT ON (ST_SnapToGrid(geom, {grid_size}))"
            vessel_order_sql = f"ORDER BY ST_SnapToGrid(geom, {grid_size}), confidence DESC, last_seen DESC"

        # Refined query — picks 1 real representative vessel per grid cell at low zoom
        sql = text(f"""
            SELECT {representative_sql}
                d.id AS v_id,
                1 AS detection_count,
                d.confidence AS avg_confidence,
                d.detection_datetime AS last_seen,
                ST_Y(d.geom) AS lat,
                ST_X(d.geom) AS lon,
                ARRAY[d.sensor_type] AS sensor_types,
                d.correlation_distance_m AS avg_dist,
                d.custom_name AS display_name,
                COALESCE(d.mmsi, 0) as real_mmsi,
                d.classification as global_classification,
                v.last_sog,
                v.last_cog
            FROM detections d
            LEFT JOIN ais_vessels v ON d.mmsi = v.mmsi
            WHERE {where_str} AND {landmask_filter}
            {vessel_order_sql}
            LIMIT :limit
        """)
        params["grid_size"] = grid_size

        result = await db.execute(sql, params)
        rows = result.fetchall()

        # AIS Info is now pre-fetched via LEFT JOIN
        ais_info = {
            int(r[9]): {"sog": r[11], "cog": r[12]}
            for r in rows
            if r[9] and int(r[9]) > 0
        }

        vessels = []
        for i, r in enumerate(rows):
            real_mmsi = int(r[9]) if r[9] else 0
            avg_dist = float(r[7]) if r[7] is not None else None
            display_name = r[8]
            db_cls = r[10]

            last_seen_str = r[3].isoformat() if r[3] else None

            anomaly_type = _classify_vessel(
                real_mmsi, avg_dist, last_seen_str, coverage, db_classification=db_cls
            )
            color = _CLASSIFICATION_COLORS.get(anomaly_type, "#6b7280")
            ais = ais_info.get(real_mmsi, {})

            vessels.append(
                {
                    "mmsi": int(real_mmsi),
                    "v_id": int(r[0]),
                    "name": str(display_name)
                    if display_name
                    else (
                        f"Vessel {real_mmsi}"
                        if real_mmsi > 0
                        else f"Unidentified {abs(int(r[0]))}"
                    ),
                    "detection_count": int(r[1]),
                    "avg_confidence": _safe_round(r[2], 4),
                    "last_seen": last_seen_str,
                    "lat": _safe_round(r[4], 6),
                    "lon": _safe_round(r[5], 6),
                    "sensor_types": [str(s) for s in list(set(r[6]))] if r[6] else [],
                    "anomaly_type": str(anomaly_type),
                    "color": str(color),
                    "is_identified": bool(
                        real_mmsi > 0 and anomaly_type == "identified"
                    ),
                    "sog": _safe_round(ais.get("sog"), 2),
                    "cog": _safe_round(ais.get("cog"), 2),
                }
            )

        return {
            "vessels": vessels,
            "total": len(vessels),
        }
    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        print(f"[Vessels API] 500 Error: {error_details}")
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "error": str(e)},
        )


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

    # --- EPHEMERAL CORRELATION FOR DETAIL ---
    final_mmsi = mmsi_val if not is_unidentified else 0
    final_name = det_rows[0][9] if (det_rows and det_rows[0][9]) else None

    if is_unidentified and det_rows:
        from backend.services.correlation import find_best_ais_match

        # Try to match the most recent detection
        r0 = det_rows[0]
        match = await find_best_ais_match(db, r0[6], r0[7], r0[4])
        if match:
            final_mmsi = match["mmsi"]
            final_name = match["name"]
            anomaly_type = "identified"

    # Fetch rich metadata from ais_vessels
    vessel_meta_res = await db.execute(
        text("SELECT * FROM ais_vessels WHERE mmsi = :mmsi"),
        {"mmsi": final_mmsi},
    )
    v_row = vessel_meta_res.fetchone()
    v_meta = dict(v_row._mapping) if v_row else {}

    return {
        "mmsi": final_mmsi,
        "v_id": mmsi,
        "name": final_name
        if final_name
        else (f"Vessel {final_mmsi}" if final_mmsi > 0 else f"Unidentified {mmsi_val}"),
        "imo": v_meta.get("imo"),
        "callSign": v_meta.get("callsign"),
        "length": v_meta.get("length"),
        "width": v_meta.get("width"),
        "draught": v_meta.get("draught"),
        "destination": v_meta.get("destination"),
        "eta": v_meta.get("eta"),
        "detection_count": len(detections),
        "anomaly_type": anomaly_type,
        "detections": detections,
        "recent_track": track,
    }
