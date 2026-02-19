import os
import csv
import cv2
import numpy as np
import rasterio
from rasterio.windows import Window
from matplotlib import pyplot as plt
import gc
import shutil

# Base paths using environment variable
root_data_dir = os.path.join("mnt", "data", "inference_images")
csv_path = os.path.join("mnt", "data", "detections", "detections_s1.csv")

# Memory optimization: reduce resolution for full scene display
DISPLAY_SCALE = 0.1  # 10% resolution for full scene

# Results folder setup
results_dir = os.path.join("mnt", "results", "additional_information")
detections_sar_dir = os.path.join(results_dir, "imagery", "detections_SAR")

# Clear detections_sar directory on each run
if os.path.exists(detections_sar_dir):
    shutil.rmtree(detections_sar_dir)
os.makedirs(detections_sar_dir, exist_ok=True)

def load_sar_image_downsampled(safe_folder, scale=0.1):
    meas_path = os.path.join(safe_folder, "measurement")
    if not os.path.exists(meas_path):
        return None, None
    for f in os.listdir(meas_path):
        if f.lower().endswith(".tiff") and "vv" in f.lower():
            img_file = os.path.join(meas_path, f)
            with rasterio.open(img_file) as src:
                original_shape = (src.height, src.width)
                out_height = int(src.height * scale)
                out_width = int(src.width * scale)
                img = src.read(
                    1,
                    out_shape=(out_height, out_width),
                    resampling=rasterio.enums.Resampling.average
                ).astype(np.float32)
                img_min, img_max = np.nanmin(img), np.nanmax(img)
                if img_max > img_min:
                    img_norm = np.clip((img - img_min) / (img_max - img_min), 0, 1)
                else:
                    img_norm = np.zeros_like(img, dtype=np.float32)
                return img_norm, original_shape
    return None, None

def read_sar_crop(safe_folder, xmin, ymin, xmax, ymax):
    meas_path = os.path.join(safe_folder, "measurement")
    if not os.path.exists(meas_path):
        return None
    for f in os.listdir(meas_path):
        if f.lower().endswith(".tiff") and "vv" in f.lower():
            img_file = os.path.join(meas_path, f)
            window = Window(xmin, ymin, xmax - xmin, ymax - ymin)
            try:
                with rasterio.open(img_file) as src:
                    img = src.read(1, window=window).astype(np.float32)
            except Exception as e:
                print(f"Error reading crop window: {e}")
                return None
            if img.size == 0:
                return None
            img_min, img_max = np.nanmin(img), np.nanmax(img)
            if img_max > img_min:
                img_norm = np.clip((img - img_min) / (img_max - img_min), 0, 1)
            else:
                img_norm = np.zeros_like(img, dtype=np.float32)
            return img_norm
    return None

def visualize():
    inferences_per_scene = {}
    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            scene = row['image_name']
            inferences_per_scene.setdefault(scene, []).append(row)

    for scene, detections in inferences_per_scene.items():
        print(f"\nProcessing scene: {scene}")
        safe_folder = os.path.join(root_data_dir, scene)

        if not os.path.isdir(safe_folder):
            print(f"Folder not found for scene {scene}")
            continue

        img_small, original_shape = load_sar_image_downsampled(safe_folder, scale=DISPLAY_SCALE)
        if img_small is None:
            print(f"Failed to load SAR image for scene {scene}")
            continue

        img_vis = (img_small * 255).astype(np.uint8)
        img_vis = cv2.cvtColor(img_vis, cv2.COLOR_GRAY2BGR)

        actual_scale = img_small.shape[0] / original_shape[0]

        for det in detections:
            try:
                xmin = int(float(det['xmin']) * actual_scale)
                ymin = int(float(det['ymin']) * actual_scale)
                xmax = int(float(det['xmax']) * actual_scale)
                ymax = int(float(det['ymax']) * actual_scale)
                cv2.rectangle(img_vis, (xmin, ymin), (xmax, ymax), (0, 255, 0), 5)
            except Exception as e:
                print(f"Error drawing bbox: {e}")

        print(f"Loading {len(detections)} detection crops...")
        crop_imgs = []
        for det in detections:
            try:
                xmin = int(float(det['xmin']))
                ymin = int(float(det['ymin']))
                xmax = int(float(det['xmax']))
                ymax = int(float(det['ymax']))
                conf = float(det['confidence'])
                xmin = max(0, xmin)
                ymin = max(0, ymin)
                xmax = min(original_shape[1], xmax)
                ymax = min(original_shape[0], ymax)
                if xmax <= xmin or ymax <= ymin:
                    continue
                crop = read_sar_crop(safe_folder, xmin, ymin, xmax, ymax)
                if crop is None or crop.size == 0:
                    continue
                crop_imgs.append((crop, conf))
            except Exception as e:
                print(f"Error reading crop: {e}")
                continue

        if not crop_imgs:
            print(f"No valid crops for scene {scene}")
            continue

        n = len(crop_imgs)
        cols = min(5, n)
        crop_rows = (n + cols - 1) // cols
        fig_height = 4 + 3 * crop_rows

        fig = plt.figure(figsize=(16, fig_height))
        # Main image top row spanning all cols
        ax_main = plt.subplot2grid((crop_rows + 1, cols), (0, 0), colspan=cols)
        ax_main.imshow(cv2.cvtColor(img_vis, cv2.COLOR_BGR2RGB))
        ax_main.set_title(f"Scene: {scene} (normalized, {int(DISPLAY_SCALE*100)}% resolution) - {n} detections")
        ax_main.axis('off')

        # Crops below
        for i, (crop, conf) in enumerate(crop_imgs):
            row = 1 + (i // cols)
            col = i % cols
            ax = plt.subplot2grid((crop_rows + 1, cols), (row, col))
            ax.imshow(crop, cmap='gray')
            ax.set_title(f"conf={conf:.2f}")
            ax.axis('off')

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        save_path = os.path.join(detections_sar_dir, f"{scene}.png")
        plt.savefig(save_path)
        plt.close()

        del img_small, img_vis, crop_imgs, fig, ax_main
        gc.collect()

        print(f"Saved combined SAR visualization for scene: {scene}")

visualize()