#!/usr/bin/env python3
"""
Batch / parallel AIS <-> detection correlation
- Implements user's algorithm (batch track loading, per-track interpolation, batch matching).
- Uses pyproj.Geod for accurate distances.
- Interpolation default: 2 minutes (120 s).
- Unmatched detections -> mmsi = 0.
- Output preserves detection order; serial numbers are continuous (1..N).
"""

import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from typing import List, Dict

import numpy as np
import pandas as pd
from pyproj import Geod
from scipy.interpolate import CubicHermiteSpline, interp1d
from tqdm import tqdm

# -------------------------
# CONFIG (tweak if needed)
# -------------------------

INPUT_DIR = Path(os.path.join("mnt", "data", "AIS"))
INFERENCE_FILE_1 = os.path.join("mnt", "data", "detections", "detections_s1.csv")
INFERENCE_FILE_2 = os.path.join("mnt", "data", "detections", "detections_s2.csv")
FILENAMES_LIST = os.path.join("mnt", "data", "AIS_correlation_image_names.txt")
OUTPUT_FILE = os.path.join("mnt", "results", "submissions", "AIS_correlation.csv")

INTERP_SECONDS = 120               # 2 minutes
# ±30 minutes temporal tolerance for matching
TIME_TOLERANCE = pd.Timedelta(minutes=5)
# distance threshold (meters) for accepting a match
LOCATION_TOLERANCE_METERS = 750
BATCH_TRACKS = 200                 # how many MMSIs to interpolate per batch
CHUNK_SIZE = 50_000                # chunk size for streaming AIS CSVs
MAX_WORKERS = max(1, (os.cpu_count() or 2) - 1)  # for parallel interpolation

# -------------------------
# geodetic helper
# -------------------------
geod = Geod(ellps="WGS84")


def geod_distance_m_vec(lat1, lon1, lat2_arr, lon2_arr):
    """Vectorized geodesic distances between a single point and arrays (meters)."""
    lon1_arr = np.full_like(lon2_arr, fill_value=lon1, dtype=float)
    lat1_arr = np.full_like(lat2_arr, fill_value=lat1, dtype=float)
    az1, az2, dist = geod.inv(lon1_arr, lat1_arr, lon2_arr, lat2_arr)
    return np.abs(dist)


def meters_to_deg_lat(m):
    return m / 111320.0


def meters_to_deg_lon(m, lat_deg):
    return m / (111320.0 * np.cos(np.radians(lat_deg)) + 1e-12)

# -------------------------
# Interpolation (physics-based)
# -------------------------


def calculate_velocity_components(lat, lon, sog, cog):
    sog_ms = sog * 0.514444  # knots -> m/s
    cog_rad = np.radians(cog)
    v_north = sog_ms * np.cos(cog_rad)
    v_east = sog_ms * np.sin(cog_rad)
    v_lat = v_north / 111320.0
    v_lon = v_east / (111320.0 * np.cos(np.radians(lat)) + 1e-12)
    return v_lat, v_lon


def interpolate_track_physics(track_df: pd.DataFrame, step_s: int = INTERP_SECONDS) -> pd.DataFrame:
    if track_df is None or len(track_df) < 2:
        return pd.DataFrame()

    df = track_df.sort_values("base_date_time").reset_index(drop=True).copy()
    df["base_date_time"] = pd.to_datetime(
        df["base_date_time"], utc=True, errors="coerce")
    df = df.dropna(subset=["base_date_time", "latitude", "longitude"])
    if len(df) < 2:
        return pd.DataFrame()

    lat_valid = df["latitude"].astype(float).to_numpy()
    lon_valid = df["longitude"].astype(float).to_numpy()
    sog_valid = df["sog"].astype(float).ffill().bfill(
    ).to_numpy() if "sog" in df.columns else np.zeros(len(df))
    cog_valid = df["cog"].astype(float).ffill().bfill(
    ).to_numpy() if "cog" in df.columns else np.zeros(len(df))

    t = pd.to_datetime(df["base_date_time"], utc=True)
    t_s = (t.dt.tz_localize(None).astype("int64") //
           1_000_000_000).to_numpy(dtype=np.int64)

    t0 = int(t_s[0])
    tn = int(t_s[-1])
    if tn <= t0:
        return pd.DataFrame()

    t_interp = np.arange(t0, tn + 1, step_s, dtype=np.int64)
    if t_interp.size == 0:
        return pd.DataFrame()

    v_lat = np.zeros_like(lat_valid, dtype=float)
    v_lon = np.zeros_like(lon_valid, dtype=float)
    for i in range(len(lat_valid)):
        v_lat[i], v_lon[i] = calculate_velocity_components(
            lat_valid[i], lon_valid[i], sog_valid[i], cog_valid[i])

    try:
        spline_lat = CubicHermiteSpline(t_s, lat_valid, v_lat)
        spline_lon = CubicHermiteSpline(t_s, lon_valid, v_lon)
        lat_interp = spline_lat(t_interp)
        lon_interp = spline_lon(t_interp)
    except Exception:
        lat_interp = np.interp(t_interp, t_s, lat_valid)
        lon_interp = np.interp(t_interp, t_s, lon_valid)

    try:
        sog_interp = interp1d(t_s, sog_valid, kind="cubic",
                              fill_value="extrapolate")(t_interp)
    except Exception:
        sog_interp = np.interp(t_interp, t_s, sog_valid)

    cog_rad = np.radians(cog_valid)
    cos_vals = np.cos(cog_rad)
    sin_vals = np.sin(cog_rad)
    try:
        cos_interp = interp1d(t_s, cos_vals, kind="cubic",
                              fill_value="extrapolate")(t_interp)
        sin_interp = interp1d(t_s, sin_vals, kind="cubic",
                              fill_value="extrapolate")(t_interp)
        cog_interp = (np.degrees(np.arctan2(sin_interp, cos_interp)) % 360.0)
    except Exception:
        cog_interp = np.interp(t_interp, t_s, cog_valid)

    df_out = pd.DataFrame({
        "base_date_time": pd.to_datetime(t_interp, unit="s", utc=True),
        "latitude": lat_interp,
        "longitude": lon_interp,
        "sog": sog_interp,
        "cog": cog_interp,
        "mmsi": int(df["mmsi"].iloc[0])
    })

    return df_out


def _interp_worker(args):
    mmsi, track_df, step_s = args
    try:
        return interpolate_track_physics(track_df, step_s=step_s)
    except Exception:
        return pd.DataFrame()

# -------------------------
# Matching routine
# -------------------------


def match_batch(interp_tracks: List[pd.DataFrame],
                det_lats: np.ndarray, det_lons: np.ndarray, det_times_s: np.ndarray,
                det_positions: np.ndarray,
                time_tol_s: int, loc_tol_m: float,
                current_best_dist: np.ndarray, current_best_mmsi: np.ndarray):

    deg_lat_rad = meters_to_deg_lat(loc_tol_m)

    for track in interp_tracks:
        if track is None or len(track) == 0:
            continue
        mmsi = int(track["mmsi"].iloc[0])
        ais_lats = track["latitude"].to_numpy(dtype=float)
        ais_lons = track["longitude"].to_numpy(dtype=float)
        ais_times_s = (track["base_date_time"].dt.tz_localize(None).astype(
            "int64") // 1_000_000_000).to_numpy(dtype=np.int64)

        tmin_lat = float(np.min(ais_lats))
        tmax_lat = float(np.max(ais_lats))
        tmin_lon = float(np.min(ais_lons))
        tmax_lon = float(np.max(ais_lons))

        lat_mask = (det_lats >= (tmin_lat - deg_lat_rad)
                    ) & (det_lats <= (tmax_lat + deg_lat_rad))
        if not np.any(lat_mask):
            continue
        cand_idx = np.nonzero(lat_mask)[0]
        cand_lats = det_lats[cand_idx]
        cand_lons = det_lons[cand_idx]

        lon_rads = meters_to_deg_lon(loc_tol_m, cand_lats)
        lon_mask = (cand_lons >= (tmin_lon - lon_rads)
                    ) & (cand_lons <= (tmax_lon + lon_rads))
        if not np.any(lon_mask):
            continue
        cand_idx = cand_idx[lon_mask]

        track_t0 = int(np.min(ais_times_s))
        track_tn = int(np.max(ais_times_s))
        cand_times = det_times_s[cand_idx]
        time_mask = (cand_times >= (track_t0 - time_tol_s)
                     ) & (cand_times <= (track_tn + time_tol_s))
        if not np.any(time_mask):
            continue
        cand_idx = cand_idx[time_mask]

        for di in cand_idx:
            det_time = int(det_times_s[di])
            time_window_mask = np.abs(ais_times_s - det_time) <= time_tol_s
            if not np.any(time_window_mask):
                continue
            pts_idx = np.nonzero(time_window_mask)[0]
            pts_lats = ais_lats[pts_idx]
            pts_lons = ais_lons[pts_idx]
            dists = geod_distance_m_vec(
                det_lats[di], det_lons[di], pts_lats, pts_lons)
            local_min_idx = int(np.argmin(dists))
            local_min_dist = float(dists[local_min_idx])
            if local_min_dist <= loc_tol_m and local_min_dist < current_best_dist[di]:
                current_best_dist[di] = local_min_dist
                current_best_mmsi[di] = mmsi

    return current_best_dist, current_best_mmsi

# -------------------------
# MAIN pipeline
# -------------------------


def main():
    for p in (INPUT_DIR, INFERENCE_FILE_1, INFERENCE_FILE_2, FILENAMES_LIST):
        if not Path(p).exists():
            raise FileNotFoundError(f"Required path not found: {p}")

    df1 = pd.read_csv(INFERENCE_FILE_1)
    df2 = pd.read_csv(INFERENCE_FILE_2)
    dets = pd.concat([df1, df2], ignore_index=True)

    with open(FILENAMES_LIST, "r") as fh:
        allowed_images = {ln.strip() for ln in fh if ln.strip()}
    dets = dets[dets["image_name"].isin(allowed_images)].copy()

    dets["detection_datetime"] = pd.to_datetime(
        dets["detection_datetime"], format="%Y-%m-%dT%H:%M:%S", utc=True, errors="coerce")
    dets = dets.dropna(
        subset=["vessel_latitude", "vessel_longitude", "detection_datetime"]).copy()

    # enforce 5-decimal precision for detections
    dets["vessel_latitude"] = dets["vessel_latitude"].round(5)
    dets["vessel_longitude"] = dets["vessel_longitude"].round(5)

    dets = dets.reset_index(drop=False).rename(columns={"index": "orig_index"})
    n_total = len(dets)

    dets["det_time_s"] = (dets["detection_datetime"].dt.tz_localize(
        None).astype("int64") // 1_000_000_000).astype(np.int64)
    det_lats_all = dets["vessel_latitude"].to_numpy(dtype=float)
    det_lons_all = dets["vessel_longitude"].to_numpy(dtype=float)
    det_times_s_all = dets["det_time_s"].to_numpy(dtype=np.int64)

    best_dist = np.full(n_total, np.inf, dtype=float)
    best_mmsi = np.zeros(n_total, dtype=np.int64)

    dets["detection_date"] = dets["detection_datetime"].dt.date
    detections_by_date = {day: group.copy()
                          for day, group in dets.groupby("detection_date")}

    ais_files = sorted([p for p in INPUT_DIR.iterdir()
                       if p.suffix.lower() == ".csv"])
    if len(ais_files) == 0:
        raise FileNotFoundError(f"No AIS CSV files found in {INPUT_DIR}")

    for day, det_group in tqdm(sorted(detections_by_date.items()), desc="Processing days"):
        day_idx = det_group.index.to_numpy(dtype=int)
        if day_idx.size == 0:
            continue

        det_min_time = det_group["detection_datetime"].min()
        det_max_time = det_group["detection_datetime"].max()
        time_min = det_min_time - TIME_TOLERANCE
        time_max = det_max_time + TIME_TOLERANCE

        mmsi_buckets: Dict[int, List[pd.DataFrame]] = {}
        for ais_fp in tqdm(ais_files, desc=f"AIS files for {day}", leave=False):
            for chunk in tqdm(pd.read_csv(ais_fp, chunksize=CHUNK_SIZE), desc=f"Chunks in {ais_fp.name}", leave=False):
                chunk.columns = [c.strip().lower() for c in chunk.columns]
                if not {"base_date_time", "latitude", "longitude", "mmsi"}.issubset(chunk.columns):
                    continue
                chunk["base_date_time"] = pd.to_datetime(
                    chunk["base_date_time"], format="%Y-%m-%d %H:%M:%S", errors="coerce", utc=True)
                chunk = chunk.dropna(
                    subset=["base_date_time", "latitude", "longitude", "mmsi"])
                if chunk.empty:
                    continue
                mask = (chunk["base_date_time"] >= time_min) & (
                    chunk["base_date_time"] <= time_max)
                sel = chunk.loc[mask, ["mmsi", "base_date_time",
                                       "latitude", "longitude", "sog", "cog"]]
                if sel.empty:
                    continue
                for m, grp in sel.groupby("mmsi"):
                    m_i = int(m)
                    if m_i not in mmsi_buckets:
                        mmsi_buckets[m_i] = [grp]
                    else:
                        mmsi_buckets[m_i].append(grp)

        full_tracks = []
        for m, parts in mmsi_buckets.items():
            try:
                dfm = pd.concat(parts, ignore_index=True).sort_values("base_date_time").drop_duplicates(
                    subset=["base_date_time", "latitude", "longitude"])
                if len(dfm) >= 2:
                    if "sog" not in dfm.columns:
                        dfm["sog"] = np.nan
                    if "cog" not in dfm.columns:
                        dfm["cog"] = np.nan
                    dfm["mmsi"] = int(m)
                    full_tracks.append((m, dfm))
            except Exception:
                continue

        if len(full_tracks) == 0:
            continue

        num_tracks = len(full_tracks)
        for bstart in tqdm(range(0, num_tracks, BATCH_TRACKS), desc=f"Batches for {day}", leave=False):
            bend = min(num_tracks, bstart + BATCH_TRACKS)
            batch = full_tracks[bstart:bend]
            args = [(m, df, INTERP_SECONDS) for (m, df) in batch]

            interp_results = []
            with ProcessPoolExecutor(max_workers=MAX_WORKERS) as exe:
                for res in exe.map(_interp_worker, args):
                    interp_results.append(res)

            if len(interp_results) == 0:
                continue

            det_positions = day_idx
            det_lats = det_lats_all[det_positions]
            det_lons = det_lons_all[det_positions]
            det_times_s = det_times_s_all[det_positions]

            best_dist_sub = best_dist[det_positions]
            best_mmsi_sub = best_mmsi[det_positions]

            best_dist_sub, best_mmsi_sub = match_batch(
                interp_results,
                det_lats, det_lons, det_times_s,
                det_positions,
                time_tol_s=int(TIME_TOLERANCE.total_seconds()),
                loc_tol_m=LOCATION_TOLERANCE_METERS,
                current_best_dist=best_dist_sub,
                current_best_mmsi=best_mmsi_sub
            )

            best_dist[det_positions] = best_dist_sub
            best_mmsi[det_positions] = best_mmsi_sub

    out = dets.copy()
    out["mmsi"] = best_mmsi
    out["time_stamp"] = pd.to_datetime(
        out["detection_datetime"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S")
    out["sl.no."] = (out["orig_index"].astype(int) + 1).astype(int)

    final = out[["sl.no.", "time_stamp", "image_name",
                 "vessel_latitude", "vessel_longitude", "mmsi"]]

    final.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved {len(final)} rows → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()