"""
AIS ↔ Detection correlation service.

Performs spatio-temporal matching between vessel detections and AIS track data
using PostGIS spatial queries + physics-based CubicHermiteSpline interpolation.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, Callable, Awaitable

import numpy as np
import pandas as pd
from pyproj import Geod
from scipy.interpolate import CubicHermiteSpline
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
INTERP_SECONDS = 120  # 2-minute interpolation step
TIME_TOLERANCE_MINUTES = 5
LOCATION_TOLERANCE_METERS = 200
BATCH_TRACKS = 200
MAX_WORKERS = max(1, (os.cpu_count() or 2) - 1)

geod = Geod(ellps="WGS84")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def run_correlation(
    db: AsyncSession,
    image_name: Optional[str] = None,
    progress_callback: Optional[Callable[[float], Awaitable[None]]] = None,
) -> int:
    """
    Run AIS-detection correlation.
    Reads detections and AIS tracks from PostGIS, matches them, and updates
    the detections table with matched MMSI.

    Returns the number of detections correlated.
    """
    # 1. Load all uncorrelated detections (optionally filtered by image)
    query = """
        SELECT id, ST_Y(geom) AS lat, ST_X(geom) AS lon,
               detection_datetime
        FROM detections
        WHERE mmsi IS NULL AND detection_datetime IS NOT NULL
    """
    params = {}
    if image_name:
        query += " AND image_name = :image_name "
        params["image_name"] = image_name

    query += " ORDER BY detection_datetime"

    result = await db.execute(text(query), params)
    det_rows = result.fetchall()
    if not det_rows:
        print("[Correlation] No uncorrelated detections found.")
        return 0

    correlated = 0
    total_detections = len(det_rows)
    for i, row in enumerate(det_rows):
        success = await correlate_single_detection(db, row[0])
        if success:
            correlated += 1
        if progress_callback and i % 50 == 0:
            progress_pct = (i / max(1, total_detections)) * 100.0
            await progress_callback(progress_pct)

    print(
        f"[Correlation] Processed {total_detections} detections. {correlated} correlated."
    )

    if progress_callback:
        await progress_callback(100.0)

    return correlated


async def correlate_single_detection(db: AsyncSession, detection_id: int) -> bool:
    """
    Perform on-the-fly strict correlation for a single detection.
    Updates the detection record if a match is found.
    """
    # 1. Fetch detection details
    res = await db.execute(
        text(
            "SELECT id, ST_Y(geom), ST_X(geom), detection_datetime FROM detections WHERE id = :id"
        ),
        {"id": detection_id},
    )
    det = res.fetchone()
    if not det:
        return False

    det_id, det_lat, det_lon, det_time = det
    match = await find_best_ais_match(db, det_lat, det_lon, det_time)

    if match:
        mmsi = match["mmsi"]
        dist = match["dist"]
        await db.execute(
            text(
                """
                UPDATE detections 
                SET mmsi = :mmsi, 
                    correlation_distance_m = :dist, 
                    custom_name = :name
                WHERE id = :id
            """
            ),
            {"mmsi": mmsi, "dist": dist, "name": match["name"], "id": det_id},
        )
        await db.commit()
        return True
    else:
        # Fallback classification
        from shared.naming import get_unidentified_name

        # Simplified dynamic classification
        u_name = get_unidentified_name(det_id)

        await db.execute(
            text("UPDATE detections SET custom_name = :name WHERE id = :id"),
            {"name": u_name, "id": det_id},
        )
        await db.commit()
        return False


async def find_best_ais_match(
    db: AsyncSession, lat: float, lon: float, dt: datetime
) -> Optional[dict]:
    """
    Find the best AIS match for a given point and time.
    Returns a dict with {mmsi, dist, name} or None.
    """
    if dt is None:
        return None
    det_time_utc = pd.to_datetime(dt, utc=True)
    if pd.isna(det_time_utc):
        return None

    time_tol = pd.Timedelta(minutes=TIME_TOLERANCE_MINUTES)
    time_min = det_time_utc - time_tol
    time_max = det_time_utc + time_tol

    query = """
    WITH ais_candidates AS (
        SELECT mmsi,
               timestamp AS t1,
               geom AS p1,
               LEAD(timestamp) OVER (PARTITION BY mmsi ORDER BY timestamp) AS t2,
               LEAD(geom) OVER (PARTITION BY mmsi ORDER BY timestamp) AS p2
        FROM ais_tracks
        WHERE timestamp BETWEEN :tmin AND :tmax
          AND ST_DWithin(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 0.1)
    )
    SELECT mmsi,
           ST_DistanceSphere(
               ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
               ST_LineInterpolatePoint(
                   ST_MakeLine(p1, p2),
                   EXTRACT(EPOCH FROM (:det_time - t1)) / EXTRACT(EPOCH FROM (t2 - t1))
               )
           ) AS dist
    FROM ais_candidates
    WHERE t1 <= :det_time AND t2 >= :det_time
      AND t2 > t1
    ORDER BY dist ASC
    LIMIT 1;
    """

    res = await db.execute(
        text(query),
        {
            "tmin": time_min.to_pydatetime(),
            "tmax": time_max.to_pydatetime(),
            "det_time": det_time_utc.to_pydatetime(),
            "lat": lat,
            "lon": lon,
        },
    )
    best_match = res.fetchone()

    if not best_match:
        return None

    best_mmsi, best_dist = best_match

    if best_mmsi > 0 and best_dist <= LOCATION_TOLERANCE_METERS:
        v_res = await db.execute(
            text("SELECT vessel_name FROM ais_vessels WHERE mmsi = :mmsi"),
            {"mmsi": best_mmsi},
        )
        v_name = v_res.scalar() or f"Vessel {best_mmsi}"
        return {"mmsi": int(best_mmsi), "dist": float(best_dist), "name": str(v_name)}

    return None


# ---------------------------------------------------------------------------
# Track interpolation (same physics-based approach)
# ---------------------------------------------------------------------------
def _calculate_velocity_components(lat, lon, sog, cog):
    sog_ms = sog * 0.514444  # knots → m/s
    cog_rad = np.radians(cog)
    v_north = sog_ms * np.cos(cog_rad)
    v_east = sog_ms * np.sin(cog_rad)
    v_lat = v_north / 111320.0
    v_lon = v_east / (111320.0 * np.cos(np.radians(lat)) + 1e-12)
    return v_lat, v_lon


def _interpolate_track_physics(
    track_df: pd.DataFrame, step_s: int = INTERP_SECONDS
) -> pd.DataFrame:
    if track_df is None or len(track_df) < 2:
        return pd.DataFrame()

    df = track_df.sort_values("base_date_time").reset_index(drop=True).copy()

    # Ensure columns exist
    if "latitude" in df.columns and "lat" not in df.columns:
        df = df.rename(columns={"latitude": "lat", "longitude": "lon"})

    df["base_date_time"] = pd.to_datetime(
        df["base_date_time"], utc=True, errors="coerce"
    )
    df = df.dropna(subset=["base_date_time", "lat", "lon"])
    if len(df) < 2:
        return pd.DataFrame()

    lat_valid = df["lat"].astype(float).to_numpy()
    lon_valid = df["lon"].astype(float).to_numpy()
    sog_valid = (
        df["sog"].astype(float).ffill().bfill().to_numpy()
        if "sog" in df.columns
        else np.zeros(len(df))
    )
    cog_valid = (
        df["cog"].astype(float).ffill().bfill().to_numpy()
        if "cog" in df.columns
        else np.zeros(len(df))
    )

    t = pd.to_datetime(df["base_date_time"], utc=True)
    t_s = t.values.astype("datetime64[ns]").astype(np.int64) // 1_000_000_000

    t0, tn = int(t_s[0]), int(t_s[-1])
    if tn <= t0:
        return pd.DataFrame()

    t_interp = np.arange(t0, tn + 1, step_s, dtype=np.int64)
    if t_interp.size == 0:
        return pd.DataFrame()

    v_lat = np.zeros_like(lat_valid, dtype=float)
    v_lon = np.zeros_like(lon_valid, dtype=float)
    for i in range(len(lat_valid)):
        v_lat[i], v_lon[i] = _calculate_velocity_components(
            lat_valid[i], lon_valid[i], sog_valid[i], cog_valid[i]
        )

    try:
        spline_lat = CubicHermiteSpline(t_s, lat_valid, v_lat)
        spline_lon = CubicHermiteSpline(t_s, lon_valid, v_lon)
        lat_interp = spline_lat(t_interp)
        lon_interp = spline_lon(t_interp)
    except Exception:
        lat_interp = np.interp(t_interp, t_s, lat_valid)
        lon_interp = np.interp(t_interp, t_s, lon_valid)

    return pd.DataFrame(
        {
            "base_date_time": pd.to_datetime(t_interp, unit="s", utc=True),
            "lat": lat_interp,
            "lon": lon_interp,
            "mmsi": int(df["mmsi"].iloc[0]),
        }
    )


def _interp_worker(args):
    mmsi, track_df, step_s = args
    try:
        return _interpolate_track_physics(track_df, step_s=step_s)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def _geod_distance_m_vec(lat1, lon1, lat2_arr, lon2_arr):
    lon1_arr = np.full_like(lon2_arr, fill_value=lon1, dtype=float)
    lat1_arr = np.full_like(lat2_arr, fill_value=lat1, dtype=float)
    _, _, dist = geod.inv(lon1_arr, lat1_arr, lon2_arr, lat2_arr)
    return np.abs(dist)


def _meters_to_deg_lat(m):
    return m / 111320.0


def _meters_to_deg_lon(m, lat_deg):
    return m / (111320.0 * np.cos(np.radians(lat_deg)) + 1e-12)


def _match_batch(
    interp_tracks,
    det_lats,
    det_lons,
    det_times_s,
    time_tol_s,
    loc_tol_m,
    current_best_dist,
    current_best_mmsi,
):
    deg_lat_rad = _meters_to_deg_lat(loc_tol_m)

    for track in interp_tracks:
        if track is None or len(track) == 0:
            continue
        mmsi = int(track["mmsi"].iloc[0])
        ais_lats = track["lat"].to_numpy(dtype=float)
        ais_lons = track["lon"].to_numpy(dtype=float)
        ais_times_s = (
            track["base_date_time"].values.astype("datetime64[ns]").astype(np.int64)
            // 1_000_000_000
        )

        tmin_lat, tmax_lat = float(np.min(ais_lats)), float(np.max(ais_lats))
        tmin_lon, tmax_lon = float(np.min(ais_lons)), float(np.max(ais_lons))

        lat_mask = (det_lats >= (tmin_lat - deg_lat_rad)) & (
            det_lats <= (tmax_lat + deg_lat_rad)
        )

        if not np.any(lat_mask):
            continue
        cand_idx = np.nonzero(lat_mask)[0]
        cand_lats = det_lats[cand_idx]
        cand_lons = det_lons[cand_idx]

        lon_rads = _meters_to_deg_lon(loc_tol_m, cand_lats)
        lon_mask = (cand_lons >= (tmin_lon - lon_rads)) & (
            cand_lons <= (tmax_lon + lon_rads)
        )
        if not np.any(lon_mask):
            continue
        cand_idx = cand_idx[lon_mask]

        track_t0 = int(np.min(ais_times_s))
        track_tn = int(np.max(ais_times_s))
        cand_times = det_times_s[cand_idx]
        time_mask = (cand_times >= (track_t0 - time_tol_s)) & (
            cand_times <= (track_tn + time_tol_s)
        )
        if not np.any(time_mask):
            continue
        cand_idx = cand_idx[time_mask]

        for di in cand_idx:
            det_time = int(det_times_s[di])
            tw_mask = np.abs(ais_times_s - det_time) <= time_tol_s
            if not np.any(tw_mask):
                continue
            pts_idx = np.nonzero(tw_mask)[0]
            dists = _geod_distance_m_vec(
                det_lats[di], det_lons[di], ais_lats[pts_idx], ais_lons[pts_idx]
            )
            local_min = int(np.argmin(dists))
            local_min_dist = float(dists[local_min])

            if local_min_dist <= loc_tol_m and local_min_dist < current_best_dist[di]:
                current_best_dist[di] = local_min_dist
                current_best_mmsi[di] = mmsi

    return current_best_dist, current_best_mmsi
