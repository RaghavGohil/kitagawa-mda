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
    zoom: int = Query(10, ge=1, le=22),
    limit: int = Query(500, ge=1, le=10000, description="Max number of MMSIs"),
    db: AsyncSession = Depends(get_db),
):
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

    # First, find distinct MMSIs in the area
    mmsi_sql = text(f"""
        SELECT DISTINCT mmsi
        FROM ais_tracks
        WHERE ST_Intersects(
            geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
        ) {time_filter} {mmsi_filter_sql}
        LIMIT :limit
    """)

    params = {
        "min_lon": min_lon,
        "min_lat": min_lat,
        "max_lon": max_lon,
        "max_lat": max_lat,
        "limit": effective_limit,
    }
    if mmsis and mmsi_list_parsed:
        params["mmsis_arr"] = mmsi_list_parsed
    if time_start:
        params["time_start"] = datetime.fromisoformat(time_start.replace("Z", "+00:00"))
    if time_end:
        params["time_end"] = datetime.fromisoformat(time_end.replace("Z", "+00:00"))

    print(
        f"[AIS] Querying tracks: limit={effective_limit}, range=({min_lon}, {min_lat}) to ({max_lon}, {max_lat})"
    )
    if time_start:
        print(f"[AIS] Time window: {time_start} to {time_end}")

    result = await db.execute(mmsi_sql, params)
    mmsi_list = [r[0] for r in result.fetchall()]
    print(f"[AIS] Found {len(mmsi_list)} vessels in area.")

    if not mmsi_list:
        return {"tracks": []}

    # For each MMSI, get the track points
    tracks = []
    for mmsi in mmsi_list:
        track_sql = text(f"""
            SELECT
                timestamp, ST_Y(geom) AS lat, ST_X(geom) AS lon,
                COALESCE(sog, 0) AS sog, COALESCE(cog, 0) AS cog
            FROM ais_tracks
            WHERE mmsi = :mmsi {time_filter}
            ORDER BY timestamp
        """)

        track_params = {"mmsi": mmsi}
        if time_start:
            track_params["time_start"] = datetime.fromisoformat(
                time_start.replace("Z", "+00:00")
            )
        if time_end:
            track_params["time_end"] = datetime.fromisoformat(
                time_end.replace("Z", "+00:00")
            )

        track_result = await db.execute(track_sql, track_params)
        points = track_result.fetchall()

        if not points:
            continue

        # Show all points as requested ("remove the zoom based logic because i want to see all ships")
        tracks.append(
            {
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
        )

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
