#!/usr/bin/env python3
import os
import csv
import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio import warp as rio_warp
from shapely.geometry import Polygon
from datetime import datetime
from ultralytics import YOLO
import torch
from tqdm import tqdm

# ------------------- Config -------------------
root_data_dir = os.path.join("mnt", "data", "inference_images")
csv_out = os.path.join("mnt", "data", "detections", "detections_s1.csv")

patch_size = 1024
stride = patch_size
conf_threshold = 0.50
batch_size = 32                       # tune by GPU memory (32 / 64 / 128)
model_path = os.path.join("inference", "imagery", "SAR", "best.pt")

model = YOLO(model_path)
device = "cuda:0" if torch.cuda.is_available() else "cpu"

# try to move model to device (some ultralytics versions manage device internally)
try:
    model.to(device)
except Exception:
    pass

# ------------------- Helpers -------------------
def parse_metadata(safe_folder):
    folder_name = os.path.basename(safe_folder)
    parts = folder_name.split('_')
    start_time = None
    end_time = None
    if len(parts) >= 7:
        try:
            start_time = datetime.strptime(parts[4], "%Y%m%dT%H%M%S")
            end_time = datetime.strptime(parts[5], "%Y%m%dT%H%M%S")
        except Exception:
            pass
    return start_time, end_time

def pixel_to_lonlat_fast(gcps_transform, gcps_crs, need_transform, x, y):
    """Transform pixel coords (x,y) -> lon,lat using precomputed transform.
       If need_transform is True, reproject from gcps_crs -> EPSG:4326."""
    lon, lat = gcps_transform * (x, y)
    if need_transform:
        xs, ys = rio_warp.transform(gcps_crs, "EPSG:4326", [lon], [lat])
        lon, lat = xs[0], ys[0]
    return float(lon), float(lat)

# ------------------- Batch inference + postprocess -------------------
def process_batch_numpy(batch_tiles_np, batch_positions, src_name,
                        gcps_transform, gcps_crs, need_transform, start_time, end_time):
    """Run YOLO on a numpy batch shaped [B,3,H,W] and return detection rows."""
    # convert to torch tensor (float32) and ensure values are in 0..1 already
    tiles = torch.tensor(batch_tiles_np, dtype=torch.float32, device=device)

    # Model predict: pass the tensor batch directly
    results = model.predict(tiles, imgsz=128, conf=conf_threshold, verbose=False, device=device)

    out = []
    for idx, res in enumerate(results):
        row, col = batch_positions[idx]
        for box in res.boxes:
            # xyxy is a tensor shape [1,4], convert to floats
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
            conf = float(box.conf[0].cpu().numpy())
            cls_id = int(box.cls[0].cpu().numpy())

            if conf < conf_threshold:
                continue

            # Translate local tile coords to global image coords
            x1g, y1g = x1 + col, y1 + row
            x2g, y2g = x2 + col, y2 + row

            # Georeference the four corners
            try:
                lonlat_coords = [
                    pixel_to_lonlat_fast(gcps_transform, gcps_crs, need_transform, x1g, y1g),
                    pixel_to_lonlat_fast(gcps_transform, gcps_crs, need_transform, x2g, y1g),
                    pixel_to_lonlat_fast(gcps_transform, gcps_crs, need_transform, x2g, y2g),
                    pixel_to_lonlat_fast(gcps_transform, gcps_crs, need_transform, x1g, y2g),
                ]
                poly = Polygon(lonlat_coords)
                centroid = poly.centroid
            except Exception:
                # skip detections we cannot georeference
                continue

            safe_folder_name = os.path.basename(os.path.dirname(os.path.dirname(src_name)))

            out.append((
                safe_folder_name,
                float(x1g), float(y1g), float(x2g), float(y2g),
                cls_id, conf,
                start_time.isoformat() if start_time else "",
                end_time.isoformat() if end_time else "",
                poly.wkt,
                float(centroid.y),
                float(centroid.x)
            ))
 
    # free some GPU memory explicitly (helps between large batches)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return out

# ------------------- Inference per SAFE folder -------------------
def run_inference_on_safe_folder(safe_folder):
    meas_path = os.path.join(safe_folder, "measurement")
    img_file = next(
        (os.path.join(meas_path, f) for f in os.listdir(meas_path)
         if f.lower().endswith(".tiff") and "vv" in f.lower()),
        None
    )
    if img_file is None:
        print(f"No VV image found in {safe_folder}")
        return []

    start_time, end_time = parse_metadata(safe_folder)
    detections = []

    with rasterio.open(img_file) as src:
        width, height = src.width, src.height

        # Precompute GCP transform and whether we need to reproject to EPSG:4326
        gcps, gcps_crs = src.get_gcps()
        if not gcps:
            print(f"WARNING: No GCPs found in {img_file}; skipping georeference.")
            return []
        gcps_transform = rasterio.transform.from_gcps(gcps)
        need_transform = True
        try:
            epsg = gcps_crs.to_epsg()
            if epsg == 4326:
                need_transform = False
        except Exception:
            need_transform = True

        # Batch buffers
        batch_tiles = []
        batch_positions = []
        batch_count = 0

        # progress iterators (rows / cols)
        for row in tqdm(range(0, height, stride), desc=f"Rows {os.path.basename(safe_folder)}"):
            for col in tqdm(range(0, width, stride), desc="Cols", leave=False):
                w_win = min(patch_size, width - col)
                h_win = min(patch_size, height - row)

                # read single band patch as float32
                patch = src.read(1, window=Window(col, row, w_win, h_win)).astype(np.float32)

                # pad to patch_size BEFORE normalization (so patch stats include pad)
                if patch.shape[0] != patch_size or patch.shape[1] != patch_size:
                    padded = np.zeros((patch_size, patch_size), dtype=np.float32)
                    padded[:patch.shape[0], :patch.shape[1]] = patch
                    patch = padded

                # normalize tile to 0..1 using min-max (robust for SAR)
                pmin = float(np.nanmin(patch))
                pmax = float(np.nanmax(patch))
                if pmax > pmin:
                    patch = (patch - pmin) / (pmax - pmin)
                else:
                    # constant tile -> zeros
                    patch = np.zeros_like(patch, dtype=np.float32)

                # stack to 3 channels in CHW: [3, H, W]
                tile_chw = np.stack([patch, patch, patch], axis=0).astype(np.float32)

                batch_tiles.append(tile_chw)
                batch_positions.append((row, col))
                batch_count += 1

                # If batch full -> run
                if batch_count >= batch_size:
                    batch_np = np.stack(batch_tiles, axis=0)  # [B,3,H,W]
                    detections.extend(
                        process_batch_numpy(batch_np, batch_positions, src.name,
                                            gcps_transform, gcps_crs, need_transform,
                                            start_time, end_time)
                    )
                    batch_tiles = []
                    batch_positions = []
                    batch_count = 0

        # leftover partial batch
        if batch_count > 0:
            batch_np = np.stack(batch_tiles, axis=0)
            detections.extend(
                process_batch_numpy(batch_np, batch_positions, src.name,
                                    gcps_transform, gcps_crs, need_transform,
                                    start_time, end_time)
            )

    return detections

# ------------------- Main driver -------------------
if __name__ == "__main__":
    if os.path.exists(csv_out):
        print(f"{csv_out} exists. Skipping inference.")
    else:
        all_safe_folders = [
            folder for folder in os.listdir(root_data_dir)
            if os.path.isdir(os.path.join(root_data_dir, folder)) and folder.startswith("S1")
        ]

        all_results = []

        for folder in tqdm(all_safe_folders, desc="SAFE folders"):
            folder_path = os.path.join(root_data_dir, folder)
            all_results.extend(run_inference_on_safe_folder(folder_path))

        csv_cols = [
            "image_name", "xmin", "ymin", "xmax", "ymax",
            "class_id", "confidence",
            "image_capture_start_datetime", "image_capture_end_datetime",
            "bbox_wkt", "vessel_latitude", "vessel_longitude"
        ]

        os.makedirs(os.path.dirname(csv_out), exist_ok=True)
        with open(csv_out, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(csv_cols)
            writer.writerows(all_results)

        print(f"Saved {len(all_results)} detections to {csv_out}")
