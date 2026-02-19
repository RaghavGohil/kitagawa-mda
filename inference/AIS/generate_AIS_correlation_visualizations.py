#!/usr/bin/env python3
"""
AIS visualizer (square-window per detection)

- For each detection, loads ALL AIS points within a square boundary (deg).
- Shows ALL AIS points inside these windows (every point is clickable).
- Shows detection markers normally.
- NO projection lines from detection → track.
"""

import os
import numpy as np
import pandas as pd
import folium
from tqdm import tqdm

# -------------------------
# Config / paths
# -------------------------
CORR_PATH = os.path.join("mnt", "results", "submissions", "AIS_correlation.csv")
AIS_DIR = os.path.join("mnt", "data", "AIS")
OUTPUT_DIR = os.path.join("mnt", "results", "additional_information", "AIS", "correlation")

os.makedirs(OUTPUT_DIR, exist_ok=True)

PRINT_PROGRESS = True
BOUNDARY_SIZE_DEG = 0.05     # +/- 0.05° window around detections (~5 km)

# -------------------------
# Load correlation file
# -------------------------
corr_df = pd.read_csv(CORR_PATH)
corr_df["time_stamp"] = pd.to_datetime(corr_df["time_stamp"], utc=True)

# -------------------------
# Map colors (random-ish)
# -------------------------
color_palette = [
    "#0066CC", "#FF6600", "#9933FF", "#00CC66", "#FF3366", "#FFCC00",
    "#00CCCC", "#CC0066", "#6600CC", "#FF9900", "#00CC99", "#CC3333",
]
mmsi_colors = {}

# -------------------------
# Main loop
# -------------------------
ais_files = [f for f in os.listdir(AIS_DIR) if f.lower().endswith(".csv")]
maps_created = 0

for ais_file in tqdm(ais_files, desc="AIS files", disable=not PRINT_PROGRESS):

    try:
        # -------------------------
        # Load AIS file
        # -------------------------
        ais_path = os.path.join(AIS_DIR, ais_file)
        ais_df = pd.read_csv(ais_path, low_memory=False)
        ais_df.columns = [c.strip().lower() for c in ais_df.columns]

        required_cols = {"latitude", "longitude", "mmsi", "base_date_time"}
        if not required_cols.issubset(ais_df.columns):
            continue

        ais_df = ais_df.dropna(subset=list(required_cols))
        ais_df["base_date_time"] = pd.to_datetime(ais_df["base_date_time"], errors="coerce", utc=True)
        ais_df = ais_df.dropna(subset=["base_date_time"])
        if ais_df.empty:
            continue

        # -------------------------
        # Determine time window for this AIS file
        # -------------------------
        time_min = ais_df["base_date_time"].min()
        time_max = ais_df["base_date_time"].max()
        time_buffer = pd.Timedelta(hours=1)

        # Only detections in extended window
        det_df = corr_df[
            (corr_df["time_stamp"] >= time_min - time_buffer) &
            (corr_df["time_stamp"] <= time_max + time_buffer)
        ].copy()

        if det_df.empty:
            continue

        # -------------------------
        # Build a unified "AIS within windows" mask
        # -------------------------
        ais_mask = np.zeros(len(ais_df), dtype=bool)

        for _, det in det_df.iterrows():
            dlat = det["vessel_latitude"]
            dlon = det["vessel_longitude"]
            if pd.isna(dlat) or pd.isna(dlon):
                continue

            # Square window filter
            lat_min = dlat - BOUNDARY_SIZE_DEG
            lat_max = dlat + BOUNDARY_SIZE_DEG
            lon_min = dlon - BOUNDARY_SIZE_DEG
            lon_max = dlon + BOUNDARY_SIZE_DEG

            submask = (
                (ais_df["latitude"] >= lat_min) &
                (ais_df["latitude"] <= lat_max) &
                (ais_df["longitude"] >= lon_min) &
                (ais_df["longitude"] <= lon_max)
            )
            ais_mask |= submask

        # Subset AIS to window
        ais_window = ais_df[ais_mask].copy()
        if ais_window.empty:
            continue

        # -------------------------
        # Make map
        # -------------------------
        center_lat = ais_window["latitude"].mean()
        center_lon = ais_window["longitude"].mean()
        m = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles="CartoDB positron")

        # -------------------------
        # Draw AIS points (clickable)
        # -------------------------
        for _, row in ais_window.iterrows():
            mmsi = int(row["mmsi"])
            if mmsi not in mmsi_colors:
                mmsi_colors[mmsi] = color_palette[len(mmsi_colors) % len(color_palette)]

            color = mmsi_colors[mmsi]

            popup_html = (
                f"<b>MMSI:</b> {mmsi}<br>"
                f"<b>Time:</b> {row['base_date_time']}<br>"
                f"<b>Lat:</b> {row['latitude']:.6f}<br>"
                f"<b>Lon:</b> {row['longitude']:.6f}"
            )

            folium.CircleMarker(
                location=(row["latitude"], row["longitude"]),
                radius=3,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.8,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"MMSI {mmsi}"
            ).add_to(m)


        # -------------------------
        # Draw track lines
        # -------------------------
        for mmsi, group in ais_window.groupby("mmsi"):
            # sort by AIS timestamp
            group = group.sort_values("base_date_time")

            # build clipped points container
            clipped_segments = []

            for _, det in det_df.iterrows():
                dlat = det["vessel_latitude"]
                dlon = det["vessel_longitude"]
                if pd.isna(dlat) or pd.isna(dlon):
                    continue
                
                # Boundary box for this detection
                lat_min = dlat - BOUNDARY_SIZE_DEG
                lat_max = dlat + BOUNDARY_SIZE_DEG
                lon_min = dlon - BOUNDARY_SIZE_DEG
                lon_max = dlon + BOUNDARY_SIZE_DEG

                # Clip AIS points to this window
                inside = group[
                    (group["latitude"] >= lat_min) &
                    (group["latitude"] <= lat_max) &
                    (group["longitude"] >= lon_min) &
                    (group["longitude"] <= lon_max)
                ]

                if len(inside) < 2:
                    continue
                
                coords = inside[["latitude", "longitude"]].values.tolist()

                clipped_segments.append(coords)

            # Render each clipped segment separately
            color = mmsi_colors.get(mmsi, "#555555")

            for seg in clipped_segments:
                folium.PolyLine(
                    locations=seg,
                    color=color,
                    weight=2,
                    opacity=0.8,
                    popup=f"MMSI {mmsi} track (clipped)"
                ).add_to(m)
        

        # -------------------------
        # Draw detection points
        # -------------------------
        for _, row in det_df.iterrows():
            det_lat = row["vessel_latitude"]
            det_lon = row["vessel_longitude"]
            if pd.isna(det_lat) or pd.isna(det_lon):
                continue

            marker_color = "#00CC00" if row.get("mmsi", 0) != 0 else "#FF0000"
            tooltip_text = f"✓ MMSI {row['mmsi']}" if row["mmsi"] != 0 else "✗ No match"

            folium.CircleMarker(
                location=[det_lat, det_lon],
                radius=7,
                color=marker_color,
                fill=True,
                fill_color=marker_color,
                fill_opacity=0.9,
                weight=3,
                popup=f"<b>MMSI:</b> {row['mmsi']}<br><b>Time:</b> {row['time_stamp']}<br><b>Scene:</b>{row['image_name']}",
                tooltip=tooltip_text
            ).add_to(m)

        # -------------------------
        # Save the map
        # -------------------------
        date_str = time_min.strftime("%Y-%m-%d")
        day_dir = os.path.join(OUTPUT_DIR, date_str)
        os.makedirs(day_dir, exist_ok=True)

        map_filename = os.path.splitext(ais_file)[0] + "_window_map.html"
        map_path = os.path.join(day_dir, map_filename)

        m.save(map_path)
        maps_created += 1
        print(f"Map saved → {map_path}")

    except Exception as e:
        print(f"Error in {ais_file}: {e}")

print(f"\n✓ Completed — {maps_created} maps created.")