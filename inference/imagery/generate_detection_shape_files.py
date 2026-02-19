from tqdm import tqdm
from shapely import wkt
from shapely.geometry import Polygon
import geopandas as gpd
import pandas as pd
import json
import os

# --------------------------- CONFIG ---------------------------
CONFIG = {
    "DETECTIONS_JSON": os.path.join("mnt", "results", "submissions", "detections.json"),
    "IMAGERY_DETAILS_CSV": os.path.join("mnt", "input", "inference_sample_data", "Imagery_details_for_vessel_detection_and_AIS_correlation.csv"),
    "INFERENCE_IMAGES_DIR": os.path.join("mnt", "data", "inference_images"),
    "OUTPUT_DIR": os.path.join("mnt", "results", "additional_information", "shapefiles"),
    "EXPORT_GEOJSON": True,       # also export .geojson alongside .shp
    "CRS": "EPSG:4326"            # WGS84 lat/lon
}
# ---------------------------------------------------------------

os.makedirs(CONFIG["OUTPUT_DIR"], exist_ok=True)

# ============================================================
# LOAD METADATA (EO + SAR blocks)
# ============================================================
print("Loading image metadata from CSV...")

eo_rows, sar_rows = [], []
current_block = None
header_found = False

with open(CONFIG["IMAGERY_DETAILS_CSV"], 'r', encoding='utf-8') as f:
    for line in f:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("EO"):
            current_block = "EO"
            header_found = False
            continue
        if stripped.startswith("SAR"):
            current_block = "SAR"
            header_found = False
            continue
        if stripped.startswith("Instructions") or stripped.startswith(",Instructions"):
            continue
        # skip the actual CSV header row (manual columns used)
        if not header_found:
            header_found = True
            continue

        if current_block == "EO":
            eo_rows.append(stripped)
        elif current_block == "SAR":
            sar_rows.append(stripped)

columns = ["S.No.(ID)", "time_stamp", "image_name",
           "image_centre_latitude", "image_centre_longitude", "Remarks"]


def parse_block(rows):
    data = []
    for row in rows:
        parts = [p.strip() for p in row.split(',')]
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        data.append(parts[:6])
    return pd.DataFrame(data, columns=columns)


eo_df = parse_block(eo_rows)
sar_df = parse_block(sar_rows)

eo_df["sensor_type"] = "EO"
sar_df["sensor_type"] = "SAR"

df = pd.concat([eo_df, sar_df], ignore_index=True)

# Type conversions
df["S.No.(ID)"] = pd.to_numeric(
    df["S.No.(ID)"], errors="coerce").astype("Int64")
df["image_centre_latitude"] = pd.to_numeric(
    df["image_centre_latitude"], errors="coerce")
df["image_centre_longitude"] = pd.to_numeric(
    df["image_centre_longitude"], errors="coerce")

# Drop invalid rows
df = df.dropna(subset=["image_name", "S.No.(ID)"])
df["image_name"] = df["image_name"].astype(str).str.strip()

# Build metadata dictionary
metadata = {}
for _, row in df.iterrows():
    folder_name = row["image_name"].strip()  # keep .SAFE
    metadata[folder_name] = {
        "id": int(row["S.No.(ID)"]),
        "timestamp": str(row["time_stamp"]),
        "lat": float(row["image_centre_latitude"]),
        "lon": float(row["image_centre_longitude"]),
        "sensor_type": row["sensor_type"]
    }

print(
    f"Loaded {len(metadata)} image entries ({len(eo_df)} EO + {len(sar_df)} SAR).")

# ============================================================
# LOAD DETECTIONS.JSON
# ============================================================
print("Reading detections JSON...")
with open(CONFIG["DETECTIONS_JSON"], "r") as f:
    detections = json.load(f)

images = {img["id"]: img for img in detections["images"]}
categories = {cat["id"]: cat["name"] for cat in detections["categories"]}

grouped = {}
for ann in detections["annotations"]:
    grouped.setdefault(ann["image_id"], []).append(ann)

print(f"Loaded {len(grouped)} annotated image entries from detections JSON.")

# ============================================================
# GENERATE SHAPEFILES + GEOJSON
# ============================================================
for image_id, anns in tqdm(grouped.items(), desc="Processing images"):
    image_info = images.get(image_id)
    if image_info is None:
        print(f"⚠️ Image ID {image_id} not found in JSON images, skipping.")
        continue

    folder_name = os.path.basename(
        image_info["file_name"]).strip()  # keep .SAFE

    if folder_name not in metadata:
        print(f"⚠️ Skipping {folder_name}: not found in metadata CSV.")
        continue

    folder_path = os.path.join(CONFIG["INFERENCE_IMAGES_DIR"], folder_name)
    if not os.path.isdir(folder_path):
        print(f"⚠️ Folder not found: {folder_path}, skipping.")
        continue

    meta = metadata[folder_name]
    records = []

    for ann in anns:
        bbox = ann.get("bbox")
        poly = None

        # WKT POLYGON
        if isinstance(bbox, str) and bbox.upper().startswith("POLYGON"):
            try:
                poly = wkt.loads(bbox)
            except Exception as e:
                print(
                    f"⚠️ Skipping annotation {ann.get('id')} due to invalid WKT: {e}")
                continue
        # YOLO-style [x, y, w, h]
        elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            try:
                x, y, w, h = bbox
                poly = Polygon(
                    [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)])
            except Exception as e:
                print(
                    f"⚠️ Skipping annotation {ann.get('id')} due to invalid bbox: {e}")
                continue
        else:
            print(
                f"⚠️ Skipping annotation {ann.get('id')} due to unsupported bbox format: {bbox}")
            continue

        if poly.is_empty or not poly.is_valid:
            print(
                f"⚠️ Skipping annotation {ann.get('id')} because polygon is invalid or empty.")
            continue

        records.append({
            "ann_id": ann.get("id"),
            "score": float(ann.get("score", 0)),
            "category": categories.get(ann.get("category_id"), "ship"),
            "image_id": int(image_id),
            "scene_id": folder_name,
            "timestamp": meta["timestamp"],
            "center_lat": meta["lat"],
            "center_lon": meta["lon"],
            "sensor_type": meta["sensor_type"],
            "geometry": poly
        })

    if not records:
        print(
            f"⚠️ No valid annotations for {folder_name}, skipping shapefile creation.")
        continue

    gdf = gpd.GeoDataFrame(records, crs=CONFIG["CRS"])

    # Save Shapefile
    shp_path = os.path.join(CONFIG["OUTPUT_DIR"], f"{folder_name}.shp")
    gdf.to_file(shp_path, driver="ESRI Shapefile")
    print(f"✅ Saved shapefile: {shp_path}")

    # # Save GeoJSON
    # if CONFIG["EXPORT_GEOJSON"]:
    #     geojson_path = os.path.join(CONFIG["OUTPUT_DIR"], f"{folder_name}.geojson")
    #     gdf.to_file(geojson_path, driver="GeoJSON")
    #     print(f"✅ Saved GeoJSON: {geojson_path}")

print("\nAll shapefiles successfully generated.")
