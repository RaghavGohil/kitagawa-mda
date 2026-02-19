from collections import Counter
from datetime import datetime
import re
from osgeo import gdal
import json
import pandas as pd
import os

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
CSV1_PATH = os.path.join("mnt", "data",
                         "detections", "detections_s1.csv")
CSV2_PATH = os.path.join("mnt", "data",
                         "detections", "detections_s2.csv")
IMAGE_NAMES_PATH = os.path.join(
    "mnt", "data", "vessel_detection_image_names.txt")
OUTPUT_PATH = os.path.join("mnt", "results",
                           "submissions", "detections.json")

# ------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------


def extract_datetime_from_filename(filename):
    """Extract datetime from Sentinel filename."""
    # S2 pattern: S2A_MSIL1C_20240904T151651_...
    # S1 pattern: S1A_IW_GRDH_1SDV_20241109T223334_...

    patterns = [
        r'_(\d{8}T\d{6})_',  # Standard pattern
        r'_(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})_'  # Alternative pattern
    ]

    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            date_str = match.group(1)
            try:
                if 'T' in date_str:
                    dt = datetime.strptime(date_str, '%Y%m%dT%H%M%S')
                else:
                    dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                print('Date parsing error:', date_str)
    return None


def get_image_dimensions(safe_path):
    """Get image dimensions from SAFE directory using GDAL."""
    try:
        # For S2 data, look for TCI.jp2 or B04.jp2
        if 'S2' in safe_path:
            granule_path = os.path.join(safe_path, 'GRANULE')
            if os.path.exists(granule_path):
                for granule in os.listdir(granule_path):
                    img_data_path = os.path.join(
                        granule_path, granule, 'IMG_DATA')
                    if os.path.exists(img_data_path):
                        # Look for any .jp2 file
                        for file in os.listdir(img_data_path):
                            if file.endswith('.jp2'):
                                jp2_path = os.path.join(img_data_path, file)
                                ds = gdal.Open(jp2_path)
                                if ds:
                                    width = ds.RasterXSize
                                    height = ds.RasterYSize
                                    ds = None
                                    return width, height

        # For S1 data, look for measurement .tiff files
        elif 'S1' in safe_path:
            measurement_path = os.path.join(safe_path, 'measurement')
            if os.path.exists(measurement_path):
                for file in os.listdir(measurement_path):
                    if file.endswith('.tiff'):
                        tiff_path = os.path.join(measurement_path, file)
                        ds = gdal.Open(tiff_path)
                        if ds:
                            width = ds.RasterXSize
                            height = ds.RasterYSize
                            ds = None
                            return width, height

        # Default fallback
        return 10980, 10980 if 'S2' in safe_path else (25800, 16700)
    except Exception as e:
        print(f"Error reading dimensions for {safe_path}: {e}")
        # Return defaults based on satellite type
        return 10980, 10980 if 'S2' in safe_path else (25800, 16700)


def get_image_info(image_name, image_id, base_path='../datasets'):
    """Get complete image information."""
    safe_path = os.path.join(base_path, image_name)

    # Extract datetime from filename
    date_captured = extract_datetime_from_filename(image_name)

    # Get dimensions
    if os.path.exists(safe_path):
        width, height = get_image_dimensions(safe_path)
    else:
        # Use defaults if path doesn't exist
        if 'S2' in image_name:
            width, height = 10980, 10980
        else:
            width, height = 25800, 16700

    return {
        "id": image_id,
        "file_name": image_name,
        "width": width,
        "height": height,
        "date_captured": date_captured if date_captured else "Unknown"
    }


# ------------------------------------------------------------
# READ IMAGE NAMES
# ------------------------------------------------------------
print("Reading image names...")
with open(IMAGE_NAMES_PATH, 'r') as f:
    image_names = [line.strip() for line in f if line.strip()]

print(f"Found {len(image_names)} images")

# ------------------------------------------------------------
# BUILD IMAGES LIST
# ------------------------------------------------------------
print("Building images list with metadata...")
images = []
image_map = {}

for idx, image_name in enumerate(image_names, start=1):
    print(f"Processing {idx}/{len(image_names)}: {image_name}")
    image_info = get_image_info(image_name, idx)
    images.append(image_info)
    image_map[image_name] = idx

# ------------------------------------------------------------
# READ CSVs
# ------------------------------------------------------------
print("\nReading inference CSVs...")
df1 = pd.read_csv(CSV1_PATH)
df2 = pd.read_csv(CSV2_PATH)
df = pd.concat([df1, df2], ignore_index=True)
print(f"Total detections: {len(df)}")

# ------------------------------------------------------------
# BUILD ANNOTATIONS
# ------------------------------------------------------------
print("Building annotations...")
annotations = []
annotation_id = 1

for i, row in df.iterrows():
    scene = str(row["image_name"]).strip()
    bbox = row["bbox_wkt"]
    score = row["confidence"]

    if scene not in image_map:
        print(f"Warning: Scene {scene} not found in image list. Skipping.")
        continue

    annotations.append({
        "id": annotation_id,
        "image_id": image_map[scene],
        "category_id": 1,
        "bbox": bbox,
        "score": float(score)
    })
    annotation_id += 1

# Sort annotations by image_id, then by annotation id
annotations = sorted(annotations, key=lambda x: (x["image_id"], x["id"]))

# Reassign annotation IDs sequentially after sorting
for idx, ann in enumerate(annotations, start=1):
    ann["id"] = idx

# ------------------------------------------------------------
# BUILD FINAL JSON
# ------------------------------------------------------------
output_json = {
    "info": {
        "description": "Grand challenge MDA",
        "version": "1.0",
        "year": 2025,
        "predicted_by": "CXON"
    },
    "licenses": [],
    "images": images,
    "categories": [
        {
            "id": 1,
            "name": "ship"
        }
    ],
    "annotations": annotations
}

# ------------------------------------------------------------
# SAVE
# ------------------------------------------------------------
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "w") as f:
    json.dump(output_json, f, indent=2)

print(f"\n✓ JSON saved to {OUTPUT_PATH}")
print(f"✓ Total images: {len(images)}")
print(f"✓ Total annotations: {len(annotations)}")

# Print summary by image
print("\nAnnotations per image:")
image_counts = Counter([ann["image_id"] for ann in annotations])
for img_id in sorted(image_counts.keys()):
    img_name = images[img_id - 1]["file_name"]
    print(f"  Image {img_id} ({img_name}): {image_counts[img_id]} detections")
