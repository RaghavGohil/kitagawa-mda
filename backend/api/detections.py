"""
Detections API — spatial queries optimized for Leaflet frontend.

Supports:
  - Bounding box queries
  - Zoom-level-based clustering (low zoom → clusters, high zoom → points)
  - GeoJSON output for direct Leaflet layer consumption
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db

router = APIRouter(prefix="/api/v1/detections", tags=["detections"])


@router.get("")
async def get_detections(
    min_lon: float = Query(..., description="Bounding box min longitude"),
    min_lat: float = Query(..., description="Bounding box min latitude"),
    max_lon: float = Query(..., description="Bounding box max longitude"),
    max_lat: float = Query(..., description="Bounding box max latitude"),
    zoom: float = Query(10, ge=1, le=22, description="Map zoom level"),
    sensor_type: Optional[str] = Query(None, description="Filter by SAR or EO"),
    limit: int = Query(1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    zoom = int(zoom)
    """
    Get detections within a bounding box.

    At zoom < 10: returns clustered centroids for performance.
    At zoom >= 10: returns individual detections.
    """
    bbox_filter = "ST_Intersects(geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))"
    sensor_filter = "AND sensor_type = :sensor" if sensor_type else ""

    if zoom < 10:
        # Cluster detections using grid-based snapping
        # Grid cell size decreases with zoom level
        cell_size = 360.0 / (2**zoom)
        sql = text(f"""
            SELECT
                COUNT(*) AS count,
                AVG(ST_Y(geom)) AS center_lat,
                AVG(ST_X(geom)) AS center_lon,
                MIN(ST_Y(geom)) AS min_lat,
                MIN(ST_X(geom)) AS min_lon,
                MAX(ST_Y(geom)) AS max_lat,
                MAX(ST_X(geom)) AS max_lon
            FROM detections
            WHERE {bbox_filter} {sensor_filter}
            GROUP BY
                FLOOR(ST_X(geom) / :cell_size),
                FLOOR(ST_Y(geom) / :cell_size)
            ORDER BY count DESC
            LIMIT :limit
        """)
        params = {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "cell_size": cell_size,
            "limit": limit,
        }
        if sensor_type:
            params["sensor"] = sensor_type

        result = await db.execute(sql, params)
        rows = result.fetchall()

        return {
            "type": "clusters",
            "zoom": zoom,
            "clusters": [
                {
                    "count": r[0],
                    "center_lat": round(r[1], 6),
                    "center_lon": round(r[2], 6),
                    "bbox": [
                        round(r[4], 6),
                        round(r[3], 6),
                        round(r[6], 6),
                        round(r[5], 6),
                    ],
                }
                for r in rows
            ],
        }
    else:
        # Return individual detections
        sql = text(f"""
            SELECT
                id, image_name, sensor_type, confidence,
                detection_datetime, mmsi,
                ST_Y(geom) AS lat, ST_X(geom) AS lon,
                bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax
            FROM detections
            WHERE {bbox_filter} {sensor_filter}
            ORDER BY confidence DESC
            LIMIT :limit
        """)
        params = {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "limit": limit,
        }
        if sensor_type:
            params["sensor"] = sensor_type

        result = await db.execute(sql, params)
        rows = result.fetchall()

        # Simple deduplication: if detections are within 0.0001 (approx 10m) of each other,
        # keep only the highest confidence one.
        detections = []
        for r in rows:
            det = {
                "id": r[0],
                "image_name": r[1],
                "sensor_type": r[2],
                "confidence": round(r[3], 4),
                "detection_datetime": r[4].isoformat() if r[4] else None,
                "mmsi": r[5],
                "lat": round(r[6], 6),
                "lon": round(r[7], 6),
                "pixel_bbox": [r[8], r[9], r[10], r[11]],
            }

            # Check if this detection overlaps significantly with an already added one
            is_duplicate = False
            for existing in detections:
                if (
                    abs(existing["lat"] - det["lat"]) < 0.0001
                    and abs(existing["lon"] - det["lon"]) < 0.0001
                ):
                    # If same image, it's definitely a duplicate or very close
                    # If different images, it's a correlation that could be merged or hidden
                    if det["image_name"] == existing["image_name"]:
                        is_duplicate = True
                        break

            if not is_duplicate:
                detections.append(det)

        return {
            "type": "points",
            "zoom": zoom,
            "detections": detections,
        }


@router.get("/geojson")
async def get_detections_geojson(
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    sensor_type: Optional[str] = None,
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """GeoJSON FeatureCollection for direct Leaflet L.geoJSON consumption."""
    sensor_filter = "AND sensor_type = :sensor" if sensor_type else ""
    sql = text(f"""
        SELECT
            id, image_name, sensor_type, confidence, mmsi,
            CAST(ST_AsGeoJSON(geom) AS json) AS geometry
        FROM detections
        WHERE ST_Intersects(
            geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
        ) {sensor_filter}
        ORDER BY confidence DESC
        LIMIT :limit
    """)
    params = {
        "min_lon": min_lon,
        "min_lat": min_lat,
        "max_lon": max_lon,
        "max_lat": max_lat,
        "limit": limit,
    }
    if sensor_type:
        params["sensor"] = sensor_type

    result = await db.execute(sql, params)
    rows = result.fetchall()

    features = []
    for r in rows:
        features.append(
            {
                "type": "Feature",
                "geometry": r[5],
                "properties": {
                    "id": r[0],
                    "image_name": r[1],
                    "sensor_type": r[2],
                    "confidence": round(r[3], 4),
                    "mmsi": r[4],
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


@router.get("/{detection_id}")
async def get_detection(
    detection_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a single detection with full details."""
    result = await db.execute(
        text("""
            SELECT
                d.id, d.image_name, d.sensor_type, d.confidence,
                d.detection_datetime, d.mmsi, d.correlation_distance_m,
                ST_Y(d.geom) AS lat, ST_X(d.geom) AS lon,
                d.bbox_xmin, d.bbox_ymin, d.bbox_xmax, d.bbox_ymax,
                d.image_capture_start, d.image_capture_end,
                ST_AsGeoJSON(d.bbox_geom) AS bbox_geojson,
                ic.minio_key
            FROM detections d
            LEFT JOIN image_chips ic ON ic.detection_id = d.id
            WHERE d.id = :det_id
        """),
        {"det_id": detection_id},
    )
    r = result.fetchone()
    if not r:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Detection not found")

    chip_url = ""
    if r[16]:  # minio_key
        from backend.services.chips import get_chip_url

        chip_url = get_chip_url(r[16])

    return {
        "id": r[0],
        "image_name": r[1],
        "sensor_type": r[2],
        "confidence": round(r[3], 4),
        "detection_datetime": r[4].isoformat() if r[4] else None,
        "mmsi": r[5],
        "correlation_distance_m": round(r[6], 2) if r[6] else None,
        "lat": round(r[7], 6),
        "lon": round(r[8], 6),
        "pixel_bbox": [r[9], r[10], r[11], r[12]],
        "image_capture_start": r[13].isoformat() if r[13] else None,
        "image_capture_end": r[14].isoformat() if r[14] else None,
        "bbox_geojson": r[15],
        "chip_url": chip_url,
    }
