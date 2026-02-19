import os
import csv
import numpy as np
import rasterio
from rasterio.windows import Window
from pyproj import Transformer
from shapely.geometry import Polygon
from datetime import datetime
from ultralytics import YOLO
import torch
from tqdm import tqdm

# ----------------------- Config -----------------------
root_data_dir = os.path.join("mnt", "data", "inference_images")
csv_path = os.path.join("mnt", "data", "detections", "detections_s2.csv")
patch_size = 512
stride = patch_size - 32 
conf_threshold = 0.80
batch_size = 32 # tune to your GPU memory
model_path = os.path.join("inference", "imagery", "EO", "best.pt")

# Load model
model = YOLO(model_path)
device = "cuda:0" if torch.cuda.is_available() else "cpu"
try:
    model.to(device)
except Exception:
    pass

# ----------------------- Helpers -----------------------
def parse_eo_metadata(safe_folder):
    start_time, stop_time = None, None
    folder_name = os.path.basename(os.path.normpath(safe_folder))
    parts = folder_name.split('_')
    if len(parts) >= 3:
        try:
            start_str = parts[2]
            start_time = datetime.strptime(start_str, '%Y%m%dT%H%M%S')
            stop_time = start_time
        except ValueError:
            pass
    return start_time, stop_time

def bbox_pixels_to_latlon(px_bbox, transform, src_crs):
    xmin, ymin, xmax, ymax = px_bbox
    if None in (transform, src_crs):
        return None, None, None
    corners_pixel = [(xmin, ymin), (xmax, ymax), (xmin, ymax), (xmax, ymin)]
    coords = [rasterio.transform.xy(transform, y, x, offset='center') for x, y in corners_pixel]
    transformer = Transformer.from_crs(src_crs.to_string(), "EPSG:4326", always_xy=True)
    latlon_coords = [transformer.transform(x, y) for x, y in coords]
    poly = Polygon(latlon_coords)
    centroid = poly.centroid
    return poly.wkt, centroid.y, centroid.x

def find_img_data_path(safe_folder):
    granule_path = os.path.join(safe_folder, "GRANULE")
    if not os.path.exists(granule_path):
        return None
    subfolders = [os.path.join(granule_path, d) for d in os.listdir(granule_path)
                  if os.path.isdir(os.path.join(granule_path, d))]
    for subfolder in subfolders:
        img_data_path = os.path.join(subfolder, "IMG_DATA")
        if os.path.exists(img_data_path):
            return img_data_path
    return None

def get_band_files(img_data_path):
    bands = {'B04': None, 'B03': None, 'B02': None}
    for f in os.listdir(img_data_path):
        for band_name in bands.keys():
            if f.endswith(f'_{band_name}.jp2'):
                bands[band_name] = os.path.join(img_data_path, f)
    return bands

def read_patch_from_bands(band_files, col, row, patch_size):
    window = Window(col, row, patch_size, patch_size)
    try:
        with rasterio.open(band_files['B04']) as src:
            r = src.read(1, window=window).astype(np.float32)
            transform = src.transform if (col == 0 and row == 0) else None
            crs = src.crs if (col == 0 and row == 0) else None
        with rasterio.open(band_files['B03']) as src:
            g = src.read(1, window=window).astype(np.float32)
        with rasterio.open(band_files['B02']) as src:
            b = src.read(1, window=window).astype(np.float32)
    except Exception:
        return None, None, None

    h, w = r.shape
    if h < patch_size or w < patch_size:
        r_padded = np.zeros((patch_size, patch_size), dtype=np.float32)
        g_padded = np.zeros((patch_size, patch_size), dtype=np.float32)
        b_padded = np.zeros((patch_size, patch_size), dtype=np.float32)
        r_padded[:h, :w] = r
        g_padded[:h, :w] = g
        b_padded[:h, :w] = b
        r, g, b = r_padded, g_padded, b_padded

    r_8bit = np.clip(r / 10000.0, 0, 1) * 255
    g_8bit = np.clip(g / 10000.0, 0, 1) * 255
    b_8bit = np.clip(b / 10000.0, 0, 1) * 255

    patch = np.dstack([r_8bit, g_8bit, b_8bit]).astype(np.uint8)
    return patch, transform, crs

def get_image_dimensions(band_file):
    with rasterio.open(band_file) as src:
        return src.height, src.width, src.transform, src.crs

def generate_patches(height, width, patch_size, stride):
    patches = []
    for row in range(0, height, stride):
        for col in range(0, width, stride):
            patches.append((row, col))
    return patches

def process_batch_numpy(batch_tiles_np, batch_positions, transform, crs,
                      start_time, stop_time):
    tiles = torch.tensor(batch_tiles_np, dtype=torch.float32, device=device) / 255.0

    results = model.predict(tiles, imgsz=512, conf=conf_threshold,
                            verbose=False, device=device)

    out = []
    for idx, res in enumerate(results):
        row, col = batch_positions[idx]
        for box in res.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
            conf = float(box.conf[0].cpu().numpy())
            cls_id = int(box.cls[0].cpu().numpy())

            if conf < conf_threshold:
                continue

            x1g, y1g = x1 + col, y1 + row
            x2g, y2g = x2 + col, y2 + row

            try:
                bbox_wkt, vessel_lat, vessel_lon = bbox_pixels_to_latlon(
                    [x1g, y1g, x2g, y2g], transform, crs
                )
                if bbox_wkt is None:
                    continue
            except Exception:
                continue

            out.append((
                os.path.basename(os.path.normpath(folder)),
                x1g, y1g, x2g, y2g,
                cls_id, conf,
                start_time.isoformat() if start_time else "",
                stop_time.isoformat() if stop_time else "",
                bbox_wkt, vessel_lat, vessel_lon
            ))
    # Free GPU cache
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return out

# ----------------------- Main inference -----------------------
def run_inference_on_safe_folder(safe_folder):
    global folder
    folder = safe_folder
    img_data_path = find_img_data_path(safe_folder)
    if img_data_path is None:
        print(f"Missing IMG_DATA in {safe_folder}")
        return []

    band_files = get_band_files(img_data_path)
    if None in band_files.values():
        print(f"Missing band files in {safe_folder}")
        return []

    height, width, transform, crs = get_image_dimensions(band_files['B04'])
    start_time, stop_time = parse_eo_metadata(safe_folder)

    patches = generate_patches(height, width, patch_size, stride)

    batch_tiles = []
    batch_positions = []
    all_detections = []

    for row, col in tqdm(patches, desc=f"Processing {os.path.basename(safe_folder)}"):

        patch, patch_transform, patch_crs = read_patch_from_bands(band_files, col, row, patch_size)
        if patch is None:
            continue

        # Convert to CHW float32 numpy
        tile_chw = np.transpose(patch, (2, 0, 1)).astype(np.float32)

        batch_tiles.append(tile_chw)
        batch_positions.append((row, col))

        if len(batch_tiles) >= batch_size:
            batch_np = np.stack(batch_tiles, axis=0)
            all_detections.extend(
                process_batch_numpy(batch_np, batch_positions, transform, crs,
                                   start_time, stop_time)
            )
            batch_tiles = []
            batch_positions = []

    # Process leftover batch
    if batch_tiles:
        batch_np = np.stack(batch_tiles, axis=0)
        all_detections.extend(
            process_batch_numpy(batch_np, batch_positions, transform, crs,
                               start_time, stop_time)
        )

    return all_detections

if __name__ == "__main__":
    if os.path.exists(csv_path):
        print(f"{csv_path} already exists. Skipping inference.")
    else:
        folder_paths = [os.path.join(root_data_dir, f) for f in os.listdir(root_data_dir)
                       if os.path.isdir(os.path.join(root_data_dir, f)) and f.startswith("S2")]

        all_results = []
        for i, folder_path in enumerate(folder_paths, 1):
            print(f"\n[{i}/{len(folder_paths)}] Processing folder: {os.path.basename(folder_path)}")
            try:
                results = run_inference_on_safe_folder(folder_path)
                all_results.extend(results)
                print(f"✓ Found {len(results)} detections")
            except Exception as e:
                print(f"✗ Error processing {folder_path}: {e}")

        csv_cols = [
            "image_name", "xmin", "ymin", "xmax", "ymax",
            "class_id", "confidence",
            "image_capture_start_datetime", "image_capture_end_datetime",
            "bbox_wkt", "vessel_latitude", "vessel_longitude"
        ]

        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(csv_cols)
            writer.writerows(all_results)

        print(f"\n✓ Saved {len(all_results)} total detections to {csv_path}")
