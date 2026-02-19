import os
import glob
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# Paths - using os.path.join with mount path
detections_folder = os.path.join("mnt", "data", "detections")  # Your detections folder path
gshhg_shp_path = os.path.join("mnt", "data", "mask", "GSHHS_shp", "f", "GSHHS_f_L1.shp")  # GSHHG shapefile

# Load land polygons and convert to EPSG:4326
land_gdf = gpd.read_file(gshhg_shp_path)
land_gdf = land_gdf.to_crs(epsg=4326)
spatial_index = land_gdf.sindex

def filter_land(df):
    keep_indices = []
    for idx, row in df.iterrows():
        lon, lat = row['vessel_longitude'], row['vessel_latitude']
        point = Point(lon, lat)
        possible_matches_index = list(spatial_index.intersection(point.bounds))
        possible_matches = land_gdf.iloc[possible_matches_index]
        on_land = any(poly.contains(point) for poly in possible_matches.geometry)
        
        print(f"Index {idx}: Point({lon}, {lat}) on_land={on_land}")
        
        if not on_land:
            keep_indices.append(idx)
    return df.loc[keep_indices]


# Find all detections CSVs in the folder starting with 'detections_s'
csv_pattern = os.path.join(detections_folder, "detections_*.csv")
csv_files = glob.glob(csv_pattern)

for csv_file in csv_files:
    print(f"Processing {os.path.basename(csv_file)}...")
    df = pd.read_csv(csv_file)
    filtered_df = filter_land(df)
    # Overwrite original file by writing filtered data back to the same path
    filtered_df.to_csv(csv_file, index=False)
    print(f"Saved filtered {len(filtered_df)} / {len(df)} detections to {os.path.basename(csv_file)}")
