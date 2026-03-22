"""
AIS ↔ Detection correlation service.

Performs spatio-temporal matching between vessel detections and AIS track data
using PostGIS spatial queries + physics-based CubicHermiteSpline interpolation.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
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
TIME_TOLERANCE_MINUTES = 10
LOCATION_TOLERANCE_METERS = 1200
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

    det_ids = np.array([r[0] for r in det_rows], dtype=np.int64)
    det_lats = np.array([r[1] for r in det_rows], dtype=np.float64)
    det_lons = np.array([r[2] for r in det_rows], dtype=np.float64)
    det_times = pd.to_datetime([r[3] for r in det_rows], utc=True)
    det_times_s = (
        det_times.values.astype("datetime64[ns]").astype(np.int64) // 1_000_000_000
    )
    best_dist = np.full(len(det_ids), np.inf, dtype=np.float64)
    best_mmsi = np.zeros(len(det_ids), dtype=np.int64)

    # 2. Group detections by date
    det_dates = det_times.date
    unique_dates = sorted(set(det_dates))

    time_tol = pd.Timedelta(minutes=TIME_TOLERANCE_MINUTES)
    time_tol_s = int(time_tol.total_seconds())

    for day in unique_dates:
        day_mask = det_dates == day
        day_idx = np.nonzero(day_mask)[0]
        if day_idx.size == 0:
            continue

        day_lats = det_lats[day_mask]
        day_lons = det_lons[day_mask]
        day_times = det_times[day_mask]

        time_min = day_times.min() - time_tol
        time_max = day_times.max() + time_tol

        # Spatially filter AIS tracks to detections area + buffer
        lat_min, lat_max = day_lats.min() - 0.2, day_lats.max() + 0.2
        lon_min, lon_max = day_lons.min() - 0.2, day_lons.max() + 0.2

        # 3. Fetch AIS tracks from PostGIS for this time window AND area
        ais_result = await db.execute(
            text("""
                SELECT mmsi, timestamp, ST_Y(geom) AS lat, ST_X(geom) AS lon,
                       COALESCE(sog, 0) AS sog, COALESCE(cog, 0) AS cog
                FROM ais_tracks
                WHERE timestamp BETWEEN :tmin AND :tmax
                  AND geom && ST_MakeEnvelope(:lon_min, :lat_min, :lon_max, :lat_max, 4326)
                ORDER BY mmsi, timestamp
            """),
            {
                "tmin": time_min.to_pydatetime(),
                "tmax": time_max.to_pydatetime(),
                "lat_min": lat_min,
                "lat_max": lat_max,
                "lon_min": lon_min,
                "lon_max": lon_max,
            },
        )
        ais_rows = ais_result.fetchall()
        print(f"[Correlation] Found {len(ais_rows)} AIS reports in AOI for {day}")
        if not ais_rows:
            continue

        # Group by MMSI
        ais_df = pd.DataFrame(
            ais_rows,
            columns=["mmsi", "base_date_time", "latitude", "longitude", "sog", "cog"],
        )
        ais_df["base_date_time"] = pd.to_datetime(ais_df["base_date_time"], utc=True)

        mmsi_groups = []
        for mmsi, grp in ais_df.groupby("mmsi"):
            grp = grp.sort_values("base_date_time").drop_duplicates(
                subset=["base_date_time", "latitude", "longitude"]
            )
            if len(grp) >= 2:
                grp["mmsi"] = int(mmsi)
                mmsi_groups.append((int(mmsi), grp))

        if not mmsi_groups:
            continue

        # 4. Interpolate tracks in batches
        for bstart in range(0, len(mmsi_groups), BATCH_TRACKS):
            batch = mmsi_groups[bstart : bstart + BATCH_TRACKS]
            args = [(m, df, INTERP_SECONDS) for m, df in batch]

            interp_results = []
            with ProcessPoolExecutor(max_workers=MAX_WORKERS) as exe:
                for res in exe.map(_interp_worker, args):
                    interp_results.append(res)

            if not interp_results:
                continue

            valid_interp = [r for r in interp_results if r is not None and len(r) > 0]
            print(
                f"[Correlation] Batch {bstart // BATCH_TRACKS}: {len(valid_interp)}/{len(batch)} tracks interpolated"
            )

            # Diagnostic for first track in first batch
            if bstart == 0 and valid_interp:
                sample_track = valid_interp[0]
                sample_t0 = sample_track["base_date_time"].min()
                sample_tn = sample_track["base_date_time"].max()
                print(
                    f"[Correlation] Sample AIS Window: {sample_t0} -> {sample_tn} (UTC)"
                )
                if len(day_times) > 0:
                    # DatetimeIndex doesn't have .iloc
                    print(f"[Correlation] Sample Det Time: {day_times[0]} (UTC)")

            if progress_callback:
                progress_pct = min(
                    90.0, ((bstart + BATCH_TRACKS) / max(1, len(mmsi_groups))) * 90.0
                )
                await progress_callback(progress_pct)

            if not valid_interp:
                continue
            d_lats = det_lats[day_idx]
            d_lons = det_lons[day_idx]
            d_times = det_times_s[day_idx]

            sub_dist = best_dist[day_idx].copy()
            sub_mmsi = best_mmsi[day_idx].copy()

            sub_dist, sub_mmsi = _match_batch(
                interp_results,
                d_lats,
                d_lons,
                d_times,
                time_tol_s,
                LOCATION_TOLERANCE_METERS,
                sub_dist,
                sub_mmsi,
            )

            best_dist[day_idx] = sub_dist
            best_mmsi[day_idx] = sub_mmsi

    # 5. Fetch Coverage for classification fallback
    from backend.api.vessels import _get_ais_coverage_dates

    coverage = await _get_ais_coverage_dates(db)

    # 6. Update detections in PostGIS with identity AND classification
    from shared.naming import get_unidentified_name

    correlated = 0
    for i in range(len(det_ids)):
        mmsi = int(best_mmsi[i])
        dist = float(best_dist[i])
        det_id = int(det_ids[i])

        # Determine 3-state classification:
        #   identified      — matched AIS, distance <= 500m
        #   anomaly         — detected in area WITH AIS coverage but no match (dark vessel)
        #   out_of_coverage — detected but no AIS data available for that area/date
        det_date_str = det_times[i].strftime("%Y-%m-%d")
        has_coverage = coverage.get(det_date_str, False)

        if mmsi != 0 and dist <= 500:
            cls_state = "identified"
            await db.execute(
                text("""
                    UPDATE detections
                    SET mmsi = :mmsi,
                        correlation_distance_m = :dist,
                        classification = :cls,
                        custom_name = COALESCE(
                            (SELECT vessel_name FROM ais_vessels WHERE mmsi = :mmsi AND vessel_name IS NOT NULL),
                            'Vessel ' || CAST(:mmsi AS VARCHAR)
                        )
                    WHERE id = :det_id
                """),
                {"mmsi": mmsi, "dist": dist, "cls": cls_state, "det_id": det_id},
            )
            correlated += 1
        else:
            # mmsi=0 (no match) OR match too far away (ambiguous) → treat as dark vessel if coverage exists
            if has_coverage:
                cls_state = (
                    "anomaly"  # Dark vessel: in coverage area, no valid AIS signal
                )
            else:
                cls_state = "out_of_coverage"  # No AIS data → cannot classify

            u_name = get_unidentified_name(int(det_ids[i]))
            await db.execute(
                text("""
                    UPDATE detections
                    SET custom_name = :name,
                        classification = :cls
                    WHERE id = :det_id
                """),
                {"name": u_name, "cls": cls_state, "det_id": det_id},
            )

        if progress_callback and i % 50 == 0:
            progress_pct = 90.0 + (i / max(1, len(det_ids))) * 10.0
            await progress_callback(progress_pct)

    await db.commit()
    print(
        f"[Correlation] Processed {len(det_ids)} detections. {correlated} correlated."
    )

    if progress_callback:
        await progress_callback(100.0)

    return correlated


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

            # Pass 1: Strict Match (Confidence)
            if local_min_dist <= loc_tol_m and local_min_dist < current_best_dist[di]:
                current_best_dist[di] = local_min_dist
                current_best_mmsi[di] = mmsi

            # Pass 2: Fallback Broad Match (Proximity)
            # If we don't have a strict match yet, but this is within 5km and is currently the best
            elif (
                current_best_dist[di] > loc_tol_m
                and local_min_dist < 5000
                and local_min_dist < current_best_dist[di]
            ):
                current_best_dist[di] = local_min_dist
                current_best_mmsi[di] = mmsi
                if di % 100 == 0:
                    print(
                        f"[Correlation] Proximity Match: Det {di} -> MMSI {mmsi} ({local_min_dist:.1f}m)"
                    )

            elif local_min_dist < 10000 and local_min_dist < current_best_dist[di]:
                # Log near misses for debugging if under 10km
                if di % 100 == 0:
                    print(
                        f"[Correlation] NEAR MISS: Det {di} is {local_min_dist:.1f}m from MMSI {mmsi}"
                    )

    return current_best_dist, current_best_mmsi
