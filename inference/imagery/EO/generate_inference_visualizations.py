import os
import csv
import cv2
import numpy as np
import rasterio
from matplotlib import pyplot as plt
import gc
import shutil

# Set base paths using environment variable
root_data_dir = os.path.join("mnt", "data", "inference_images")
csv_path = os.path.join("mnt",  "data", "detections", "detections_s2.csv")

# Memory optimization: reduce resolution for full scene display
DISPLAY_SCALE = 0.1  # 10% resolution for full scene

# Define results directory and subfolder detections_EO
results_dir = os.path.join("mnt", "results", "additional_information")
detections_eo_dir = os.path.join(results_dir, "imagery", "detections_EO")

# Clear the detections_EO directory or create if it doesn't exist
if os.path.exists(detections_eo_dir):
    shutil.rmtree(detections_eo_dir)  # Delete folder and all contents
os.makedirs(detections_eo_dir, exist_ok=True)

def find_img_data_path(safe_folder):
    granule_path = os.path.join(safe_folder, "GRANULE")
    if not os.path.exists(granule_path):
        return None
    for d in os.listdir(granule_path):
        img_data = os.path.join(granule_path, d, "IMG_DATA")
        if os.path.exists(img_data):
            return img_data
    return None

def read_normalized_rgb_downsampled(img_data_path, scale=0.1):
    """
    Memory-efficient: Load bands at reduced resolution with simple normalization.
    """
    band_files = {}
    for f in os.listdir(img_data_path):
        if f.endswith("_B04.jp2"): 
            band_files["R"] = os.path.join(img_data_path, f)
        elif f.endswith("_B03.jp2"): 
            band_files["G"] = os.path.join(img_data_path, f)
        elif f.endswith("_B02.jp2"): 
            band_files["B"] = os.path.join(img_data_path, f)
    
    if len(band_files) < 3:
        return None, None

    with rasterio.open(band_files["R"]) as rsrc:
        out_height = int(rsrc.height * scale)
        out_width = int(rsrc.width * scale)
        original_shape = (rsrc.height, rsrc.width)
        r = rsrc.read(1, out_shape=(out_height, out_width)).astype(np.float32)
    
    with rasterio.open(band_files["G"]) as gsrc:
        g = gsrc.read(1, out_shape=(out_height, out_width)).astype(np.float32)
    
    with rasterio.open(band_files["B"]) as bsrc:
        b = bsrc.read(1, out_shape=(out_height, out_width)).astype(np.float32)

    # Simple normalization: divide by 10000 (standard Sentinel-2 reflectance scale)
    r_norm = np.clip(r / 10000.0, 0, 1)
    g_norm = np.clip(g / 10000.0, 0, 1)
    b_norm = np.clip(b / 10000.0, 0, 1)
    
    # Stack RGB
    rgb = np.dstack([r_norm, g_norm, b_norm])
    
    return rgb, original_shape

def read_crop_normalized(img_data_path, xmin, ymin, xmax, ymax):
    """
    Read only the crop region from disk with simple normalization.
    """
    band_files = {}
    for f in os.listdir(img_data_path):
        if f.endswith("_B04.jp2"): 
            band_files["R"] = os.path.join(img_data_path, f)
        elif f.endswith("_B03.jp2"): 
            band_files["G"] = os.path.join(img_data_path, f)
        elif f.endswith("_B02.jp2"): 
            band_files["B"] = os.path.join(img_data_path, f)
    
    if len(band_files) < 3:
        return None
    
    # Define window for crop
    window = rasterio.windows.Window(xmin, ymin, xmax - xmin, ymax - ymin)
    
    try:
        with rasterio.open(band_files["R"]) as rsrc:
            r = rsrc.read(1, window=window).astype(np.float32)
        
        with rasterio.open(band_files["G"]) as gsrc:
            g = gsrc.read(1, window=window).astype(np.float32)
        
        with rasterio.open(band_files["B"]) as bsrc:
            b = bsrc.read(1, window=window).astype(np.float32)
    except Exception as e:
        print(f"Error reading crop window: {e}")
        return None
    
    if r.size == 0 or g.size == 0 or b.size == 0:
        return None
    
    # Simple normalization: divide by 10000
    r_norm = np.clip(r / 10000.0, 0, 1)
    g_norm = np.clip(g / 10000.0, 0, 1)
    b_norm = np.clip(b / 10000.0, 0, 1)
    
    rgb = np.dstack([r_norm, g_norm, b_norm])
    
    return rgb

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
        img_data_path = find_img_data_path(safe_folder)
        if img_data_path is None:
            print(f"IMG_DATA folder not found for scene {scene}")
            continue

        # Load downsampled full scene
        img_small, original_shape = read_normalized_rgb_downsampled(img_data_path, scale=DISPLAY_SCALE)
        if img_small is None:
            print(f"Failed to load RGB image for scene {scene}")
            continue

        img_vis = (img_small * 255).astype(np.uint8).copy()

        # Calculate scale factor
        actual_scale = img_small.shape[0] / original_shape[0]

        # Draw boxes
        for det in detections:
            try:
                xmin = int(float(det['xmin']) * actual_scale)
                ymin = int(float(det['ymin']) * actual_scale)
                xmax = int(float(det['xmax']) * actual_scale)
                ymax = int(float(det['ymax']) * actual_scale)
                cv2.rectangle(img_vis, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
            except Exception as e:
                print(f"Error drawing bbox: {e}")

        # Load crop images
        print(f"Loading {len(detections)} detection crops...")
        crop_imgs = []
        for det in detections:
            try:
                xmin = int(float(det['xmin']))
                ymin = int(float(det['ymin']))
                xmax = int(float(det['xmax']))
                ymax = int(float(det['ymax']))
                conf = float(det['confidence'])
                crop = read_crop_normalized(img_data_path, xmin, ymin, xmax, ymax)
                if crop is None or crop.size == 0:
                    continue
                crop_imgs.append((crop, conf))
            except Exception as e:
                print(f"Error reading crop: {e}")
                continue

        if not crop_imgs:
            print(f"No valid crops for scene {scene}")
            continue

        # Calculate layout: 1 row for full image + rows for crops (5 crops per row max)
        n = len(crop_imgs)
        crops_per_row = 5
        crop_rows = (n + crops_per_row - 1) // crops_per_row
        fig_height = 4 + 3 * crop_rows  # allocate height for main image + crops

        fig = plt.figure(figsize=(16, fig_height))

        # Main image on top, spans all columns
        ax_main = plt.subplot2grid((crop_rows + 1, crops_per_row), (0, 0), colspan=crops_per_row)
        ax_main.imshow(img_vis)
        ax_main.set_title(f"Scene: {scene} (normalized, {int(DISPLAY_SCALE*100)}% resolution)")
        ax_main.axis('off')

        # Plot crops below
        for i, (crop, conf) in enumerate(crop_imgs):
            row = 1 + (i // crops_per_row)
            col = i % crops_per_row
            ax = plt.subplot2grid((crop_rows + 1, crops_per_row), (row, col))
            ax.imshow(np.clip(crop, 0, 1))
            ax.set_title(f"conf={conf:.2f}")
            ax.axis('off')

        plt.tight_layout(rect=[0, 0, 1, 0.95])  # adjust layout to avoid overlap
        save_path_combined = os.path.join(detections_eo_dir, f"{scene}.png")
        plt.savefig(save_path_combined)
        plt.close()

        # Free memory
        del img_small, img_vis, crop_imgs, fig, ax_main
        gc.collect()

        print(f"Saved combined visualization for scene: {scene}")

visualize()
