#!/usr/bin/env python3
"""
Fast AIS Tracks Only (max 10 points per track)

- Shows ONLY track lines (no individual points)
- Max 10 points per MMSI (most recent)
- Optimized for speed
"""

import os
import pandas as pd
import folium
from tqdm import tqdm

# -------------------------
# Config / paths
# -------------------------
AIS_DIR = os.path.join("mnt", "data", "AIS")
OUTPUT_DIR = os.path.join("mnt", "results", "additional_information", "AIS", "all_tracks")

os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_POINTS_PER_TRACK = 10

# -------------------------
# Color scheme (global to reuse across files)
# -------------------------
color_palette = [
    "#0066CC", "#FF6600", "#9933FF", "#00CC66", "#FF3366", "#FFCC00",
    "#00CCCC", "#CC0066", "#6600CC", "#FF9900", "#00CC99", "#CC3333",
]

# -------------------------
# Main loop
# -------------------------
ais_files = [f for f in os.listdir(AIS_DIR) if f.lower().endswith(".csv")]
maps_created = 0

for ais_file in tqdm(ais_files, desc="AIS files"):
    try:
        ais_path = os.path.join(AIS_DIR, ais_file)
        
        # FAST CSV read - only required columns
        ais_df = pd.read_csv(
            ais_path, 
            usecols=["latitude", "longitude", "mmsi", "base_date_time"],
            dtype={"latitude": "float32", "longitude": "float32", "mmsi": "int64"}
        )
        ais_df.columns = [c.strip().lower() for c in ais_df.columns]
        
        # Clean + datetime (single operation)
        ais_df = ais_df.dropna(subset=["latitude", "longitude", "mmsi"])
        ais_df["base_date_time"] = pd.to_datetime(ais_df["base_date_time"], utc=True)
        
        if ais_df.empty:
            continue

        # -------------------------
        # FAST map creation
        # -------------------------
        center_lat = ais_df["latitude"].mean()
        center_lon = ais_df["longitude"].mean()
        m = folium.Map([center_lat, center_lon], zoom_start=10, tiles="CartoDB positron")

        # -------------------------
        # TRACKS ONLY - super fast
        # -------------------------
        color_idx = 0
        for mmsi, group in ais_df.groupby("mmsi", sort=False):
            # Most recent 10 points
            track = group.sort_values("base_date_time").tail(MAX_POINTS_PER_TRACK)
            
            if len(track) >= 2:
                coords = track[["latitude", "longitude"]].values.tolist()
                color = color_palette[color_idx % len(color_palette)]
                
                folium.PolyLine(
                    coords, 
                    color=color, 
                    weight=4, 
                    opacity=0.9,
                    popup=f"MMSI {mmsi} ({len(coords)} pts)"
                ).add_to(m)
                
                color_idx += 1

        # -------------------------
        # Save
        # -------------------------
        date_str = ais_df["base_date_time"].min().strftime("%Y-%m-%d")
        day_dir = os.path.join(OUTPUT_DIR, date_str)
        os.makedirs(day_dir, exist_ok=True)
        
        outpath = os.path.join(day_dir, f"{os.path.splitext(os.path.basename(ais_file))[0]}_tracks.html")
        m.save(outpath)
        maps_created += 1

    except Exception as e:
        print(f"Error {ais_file}: {e}")

print(f"\n✓ {maps_created} track maps created.")
