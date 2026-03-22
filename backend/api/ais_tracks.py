"""
AIS Tracks API — spatial + temporal queries for Leaflet track visualization.

Supports:
  - Bounding box + time range queries
  - Track simplification at low zoom levels (Douglas-Peucker via PostGIS)
  - GeoJSON LineString output for Leaflet polylines
  - Per-MMSI full track retrieval
"""

from __future__ import annotations
import math
from datetime import datetime

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db

router = APIRouter(prefix="/api/v1/ais", tags=["ais_tracks"])


@router.get("/tracks")
async def get_ais_tracks(
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    time_start: Optional[str] = Query(None, description="ISO timestamp start"),
    time_end: Optional[str] = Query(None, description="ISO timestamp end"),
    mmsis: Optional[str] = Query(None, description="Comma-separated list of MMSIs"),
    zoom: float = Query(10, ge=1, le=22),
    limit: int = Query(2000, ge=1, le=10000, description="Max number of MMSIs"),
    db: AsyncSession = Depends(get_db),
):
    zoom = int(zoom)
    """
    Get AIS tracks within a bounding box and optional time range.

    Returns tracks grouped by MMSI. At low zoom levels, track geometry
    is simplified using Douglas-Peucker to reduce point count.
    """
    time_filter = ""
    if time_start:
        time_filter += " AND timestamp >= CAST(:time_start AS timestamptz)"
    if time_end:
        time_filter += " AND timestamp <= CAST(:time_end AS timestamptz)"

    # Always show tracks
    effective_limit = limit

    mmsi_filter_sql = ""
    if mmsis:
        mmsi_list_parsed = [
            int(m.strip()) for m in mmsis.split(",") if m.strip().isdigit()
        ]
        if mmsi_list_parsed:
            mmsi_filter_sql = " AND mmsi = ANY(:mmsis_arr)"

    # Tolerance for point simplification based on zoom
    tolerance = 0.1 / (2 ** (max(1, zoom - 1)))

    # Dynamic point limit based on zoom to prevent massive payloads at low zoom
    # z=1-5: 20 pts, z=6-10: 50 pts, z=11-15: 100 pts, z>15: 200 pts
    point_limit = 20
    if zoom > 5:
        point_limit = 50
    if zoom > 10:
        point_limit = 100
    if zoom > 15:
        point_limit = 200

    # Grid-based sampling for "Representative Ships" at low zoom
    # This prevents UI lag by picking 1 real vessel per grid cell
    representative_sql = ""
    if zoom < 12:
        # Cell size in degrees. z=3: ~2deg, z=11: ~0.01deg
        cell_size = 180.0 / (2**zoom)
        representative_sql = f"DISTINCT ON (ST_SnapToGrid(geom, {cell_size}))"
        # Since we use DISTINCT ON, we need an ORDER BY that matches
        mmsi_order_sql = f"ORDER BY ST_SnapToGrid(geom, {cell_size}), timestamp DESC"
    else:
        mmsi_order_sql = "ORDER BY timestamp DESC"

    # Optimized single query using LATERAL join for "Top-N per group" performance
    # target_mmsis uses grid-based sampling at low zoom to pick representatives
    sql = text(f"""
        WITH target_mmsis AS (
            SELECT {representative_sql} mmsi
            FROM ais_tracks
            WHERE ST_Intersects(
                geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
            ) {time_filter} {mmsi_filter_sql}
            {mmsi_order_sql}
            LIMIT :limit
        )
        SELECT
            m.mmsi,
            jsonb_agg(
                jsonb_build_object(
                    'timestamp', t.timestamp,
                    'lat', ROUND(ST_Y(ST_SnapToGrid(t.geom, :tolerance))::numeric, 6),
                    'lon', ROUND(ST_X(ST_SnapToGrid(t.geom, :tolerance))::numeric, 6),
                    'sog', ROUND(COALESCE(t.sog, 0)::numeric, 2),
                    'cog', ROUND(COALESCE(t.cog, 0)::numeric, 2)
                ) ORDER BY t.timestamp
            ) AS points
        FROM target_mmsis m
        CROSS JOIN LATERAL (
            SELECT timestamp, geom, sog, cog
            FROM ais_tracks
            WHERE mmsi = m.mmsi
              AND ST_Intersects(
                  geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
              ) {time_filter}
            ORDER BY timestamp DESC
            LIMIT :point_limit
        ) t
        GROUP BY m.mmsi
    """)

    params = {
        "min_lon": min_lon,
        "min_lat": min_lat,
        "max_lon": max_lon,
        "max_lat": max_lat,
        "tolerance": tolerance,
        "limit": effective_limit,
        "point_limit": point_limit,
    }
    if mmsis and mmsi_list_parsed:
        params["mmsis_arr"] = mmsi_list_parsed
    if time_start:
        params["time_start"] = datetime.fromisoformat(time_start.replace("Z", "+00:00"))
    if time_end:
        params["time_end"] = datetime.fromisoformat(time_end.replace("Z", "+00:00"))

    print(
        f"[AIS] Lateral Query: limit={effective_limit}, zoom={zoom}, range=({min_lon}, {min_lat}) to ({max_lon}, {max_lat})"
    )

    result = await db.execute(sql, params)
    rows = result.fetchall()

    tracks = []
    for r in rows:
        # Deduplicate points that snapped to the same grid location
        seen_coords = set()
        unique_points = []
        for p in r[1]:
            coord = (p["lat"], p["lon"])
            if coord not in seen_coords:
                unique_points.append(p)
                seen_coords.add(coord)

        tracks.append(
            {
                "mmsi": r[0],
                "point_count": len(unique_points),
                "points": unique_points,
            }
        )

    return {"tracks": tracks, "total_vessels": len(tracks)}

    return {"tracks": tracks, "total_vessels": len(tracks)}


@router.get("/tracks/{mmsi}")
async def get_track_by_mmsi(
    mmsi: int,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get the full track for a specific vessel by MMSI."""
    time_filter = ""
    params = {"mmsi": mmsi}
    if time_start:
        time_filter += " AND timestamp >= CAST(:time_start AS timestamptz)"
        params["time_start"] = datetime.fromisoformat(time_start.replace("Z", "+00:00"))
    if time_end:
        time_filter += " AND timestamp <= CAST(:time_end AS timestamptz)"
        params["time_end"] = datetime.fromisoformat(time_end.replace("Z", "+00:00"))

    result = await db.execute(
        text(f"""
            SELECT
                timestamp, ST_Y(geom) AS lat, ST_X(geom) AS lon,
                COALESCE(sog, 0) AS sog, COALESCE(cog, 0) AS cog
            FROM ais_tracks
            WHERE mmsi = :mmsi {time_filter}
            ORDER BY timestamp
        """),
        params,
    )
    points = result.fetchall()

    return {
        "mmsi": mmsi,
        "point_count": len(points),
        "points": [
            {
                "timestamp": p[0].isoformat() if p[0] else None,
                "lat": round(p[1], 6)
                if p[1] is not None and math.isfinite(p[1])
                else 0.0,
                "lon": round(p[2], 6)
                if p[2] is not None and math.isfinite(p[2])
                else 0.0,
                "sog": round(p[3], 2)
                if p[3] is not None and math.isfinite(p[3])
                else 0.0,
                "cog": round(p[4], 2)
                if p[4] is not None and math.isfinite(p[4])
                else 0.0,
            }
            for p in points
        ],
    }


@router.get("/tracks/geojson")
async def get_tracks_geojson(
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
    zoom: int = Query(10, ge=1, le=22),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    GeoJSON FeatureCollection of AIS tracks as LineStrings.
    Simplified at low zoom for Leaflet performance.
    """
    time_filter = ""
    params = {
        "min_lon": min_lon,
        "min_lat": min_lat,
        "max_lon": max_lon,
        "max_lat": max_lat,
        "limit": limit,
    }
    if time_start:
        time_filter += " AND timestamp >= CAST(:time_start AS timestamptz)"
        params["time_start"] = datetime.fromisoformat(time_start.replace("Z", "+00:00"))
    if time_end:
        time_filter += " AND timestamp <= CAST(:time_end AS timestamptz)"
        params["time_end"] = datetime.fromisoformat(time_end.replace("Z", "+00:00"))

    # Tolerance for line simplification based on zoom
    tolerance = max(0.0001, 1.0 / (2**zoom))

    sql = text(f"""
        WITH vessel_tracks AS (
            SELECT
                mmsi,
                ST_MakeLine(geom ORDER BY timestamp) AS track_geom
            FROM ais_tracks
            WHERE ST_Intersects(
                geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
            ) {time_filter}
            GROUP BY mmsi
            HAVING COUNT(*) >= 2
            LIMIT :limit
        )
        SELECT
            mmsi,
            CAST(ST_AsGeoJSON(ST_Simplify(track_geom, :tolerance)) AS json) AS geometry
        FROM vessel_tracks
    """)
    params["tolerance"] = tolerance

    result = await db.execute(sql, params)
    rows = result.fetchall()

    features = [
        {
            "type": "Feature",
            "geometry": r[1],
            "properties": {"mmsi": r[0]},
        }
        for r in rows
    ]

    return {
        "type": "FeatureCollection",
        "features": features,
    }


@router.get("/coverage-grid")
async def get_ais_coverage_grid(
    min_lon: float = Query(-180),
    min_lat: float = Query(-90),
    max_lon: float = Query(180),
    max_lat: float = Query(90),
    grid_size: float = Query(
        1.0, ge=0.1, le=5.0, description="Grid cell size in degrees"
    ),
    days: int = Query(30, ge=1, le=365, description="How many days back to look"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a GeoJSON grid of AIS reception density.
    Each cell shows the count of distinct MMSIs seen, enabling
    synthetic coverage visualization (where AIS data was received).
    """
    sql = text("""
        SELECT
            FLOOR((ST_X(geom) - :min_lon) / :grid_size) AS col,
            FLOOR((ST_Y(geom) - :min_lat) / :grid_size) AS row,
            COUNT(DISTINCT mmsi) AS vessel_count
        FROM ais_tracks
        WHERE timestamp > NOW() - (:days * INTERVAL '1 day')
          AND geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
        GROUP BY col, row
        HAVING COUNT(DISTINCT mmsi) > 0
        ORDER BY vessel_count DESC
        LIMIT 5000
    """)

    result = await db.execute(
        sql,
        {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "grid_size": grid_size,
            "days": days,
        },
    )
    rows = result.fetchall()

    features = []
    max_count = max((r[2] for r in rows), default=1)

    for r in rows:
        col, row_idx, count = int(r[0]), int(r[1]), int(r[2])
        west = min_lon + col * grid_size
        south = min_lat + row_idx * grid_size
        east = west + grid_size
        north = south + grid_size
        # Normalize intensity 0-1
        intensity = round(count / max_count, 3)

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [west, south],
                            [east, south],
                            [east, north],
                            [west, north],
                            [west, south],
                        ]
                    ],
                },
                "properties": {
                    "vessel_count": count,
                    "intensity": intensity,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"total_cells": len(features), "max_count": max_count},
    }
