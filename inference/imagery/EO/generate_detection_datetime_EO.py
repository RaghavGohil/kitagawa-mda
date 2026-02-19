#!/usr/bin/env python3

import os
import csv
import sys
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from osgeo import gdal  # Correct GDAL import for Python bindings

# Config
root_data_dir = os.path.join("mnt", "data", "inference_images")
csv_file = os.path.join("mnt", "data", "detections", "detections_s2.csv")

SENSOR_VELOCITY_KMS = 7.5  # Sentinel-2 spacecraft speed in km/s
GRANULE_SIZE_KM = 100.0  # Approximate granule size in km

def find_granule_folder(safe_folder):
    granule_dir = os.path.join(safe_folder, "GRANULE")
    if not os.path.isdir(granule_dir):
        return None
    entries = [os.path.join(granule_dir, d) for d in os.listdir(granule_dir)]
    granules = [e for e in entries if os.path.isdir(e)]
    return granules[0] if granules else None

def parse_sensing_time(mtd_tl_xml_path):
    try:
        tree = ET.parse(mtd_tl_xml_path)
        root = tree.getroot()
        
        # Try direct find (no namespace)
        sensing_elem = root.find("SENSING_TIME")
        
        # Fallback: manual find ignoring namespaces
        if sensing_elem is None:
            sensing_elem = None
            for elem in root.iter():
                if elem.tag.endswith('SENSING_TIME'):
                    sensing_elem = elem
                    break
        
        if sensing_elem is None or not sensing_elem.text:
            print(f"[WARN] SENSING_TIME not found in {mtd_tl_xml_path}")
            return None
        
        sensing_time_str = sensing_elem.text.strip()
        # Remove trailing 'Z' if present (UTC indicator)
        if sensing_time_str.endswith('Z'):
            sensing_time_str = sensing_time_str[:-1]
        sensing_time = datetime.fromisoformat(sensing_time_str)
        return sensing_time
    except Exception as e:
        print(f"[ERROR] Failed to parse sensing time: {e}")
        return None

def estimate_granule_duration_seconds():
    return GRANULE_SIZE_KM / SENSOR_VELOCITY_KMS

def get_image_height_from_gdal(granule_folder):
    img_data = os.path.join(granule_folder, "IMG_DATA")
    if not os.path.isdir(img_data):
        return None
    for f in os.listdir(img_data):
        if f.endswith("_B04.jp2"):
            img_path = os.path.join(img_data, f)
            ds = gdal.Open(img_path)
            if ds:
                height = ds.RasterYSize
                ds = None  # Close dataset
                return height
    return None

def find_granule_image_height(granule_folder):
    height = get_image_height_from_gdal(granule_folder)
    if height is not None:
        return height
    return 10980  # Fallback typical Sentinel-2 height

def main():
    if not os.path.exists(csv_file):
        print(f"[ERR] CSV file not found: {csv_file}", file=sys.stderr)
        sys.exit(1)

    with open(csv_file, 'r', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames if reader.fieldnames else []
        if "detection_datetime" not in fieldnames:
            fieldnames.append("detection_datetime")

    sensing_cache = {}
    granule_duration = estimate_granule_duration_seconds()
    n_with_time = 0

    for row in rows:
        try:
            safe_name = row["image_name"]
            ymin = float(row["ymin"])
            ymax = float(row["ymax"])
            line_idx = 0.5 * (ymin + ymax)
        except Exception:
            row["detection_datetime"] = ""
            continue

        if safe_name in sensing_cache:
            sensing_time, img_height = sensing_cache[safe_name]
        else:
            safe_folder = os.path.join(root_data_dir, safe_name)
            granule_folder = find_granule_folder(safe_folder)
            sensing_time, img_height = None, None
            if granule_folder:
                mtd_tl_xml_path = os.path.join(granule_folder, "MTD_TL.xml")
                if os.path.exists(mtd_tl_xml_path):
                    sensing_time = parse_sensing_time(mtd_tl_xml_path)
                    img_height = find_granule_image_height(granule_folder)
            sensing_cache[safe_name] = (sensing_time, img_height)

        if sensing_time is None or img_height is None:
            row["detection_datetime"] = ""
            continue

        frac = min(max(line_idx / img_height, 0), 1)
        delta_seconds = frac * granule_duration
        det_time = sensing_time + timedelta(seconds=delta_seconds)
        row["detection_datetime"] = det_time.strftime("%Y-%m-%dT%H:%M:%S")
        n_with_time += 1

    with open(csv_file, 'w', newline='') as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Updated {csv_file} with detection_datetime for {n_with_time} rows.")

if __name__ == "__main__":
    main()
