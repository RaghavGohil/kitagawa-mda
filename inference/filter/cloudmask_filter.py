import os
import csv
import cv2
import numpy as np
import rasterio
import shutil
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import torch
from torchvision import transforms
from torchvision.models import convnext_tiny, ConvNeXt_Tiny_Weights
import torch.nn as nn
import zipfile

path = os.path.join("inference", "filter")

base_archive = os.path.join(path, "cloudmask.zip")


def combine_parts():
    # Find split ZIP parts inside the directory
    parts = sorted(
        [
            os.path.join(path, p)
            for p in os.listdir(path)
            if p.startswith("cloudmask.zip.part.")
        ]
    )

    if not parts:
        raise FileNotFoundError("No split parts found in inference/filter/")

    print("Combining parts into a single ZIP...")

    # Rebuild the main ZIP archive
    with open(base_archive, "wb") as outfile:
        for p in parts:
            print(f"→ Adding {p}")
            with open(p, "rb") as partfile:
                outfile.write(partfile.read())

    print(f"Recombined into: {base_archive}")


def unzip_model():
    print(f"Extracting {base_archive} ...")
    with zipfile.ZipFile(base_archive, "r") as zipf:
        zipf.extractall(path)  # Extract inside inference/filter/
    print("Model extracted successfully.")


combine_parts()
unzip_model()
print("\nModel reconstruction complete!")

# ============================================================
# Constants / Paths
# ============================================================
ROOT_DATA_DIR = os.path.join("mnt", "data", "inference_images")
CSV_PATH = os.path.join("mnt", "data", "detections", "detections_s2.csv")
CROP_DIR = os.path.join(
    "mnt", "data", "cloudmask_crops"
)
PATCH_SIZE = 32
MODEL_INPUT_SIZE = 128
CONF_THRESHOLD = 0.57
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Clear/create results directory
if os.path.exists(CROP_DIR):
    shutil.rmtree(CROP_DIR)
os.makedirs(CROP_DIR, exist_ok=True)


# ============================================================
# Helper Functions for Sentinel-2
# ============================================================
def find_img_data_path(safe_folder):
    try:
        granule_path = os.path.join(safe_folder, "GRANULE")
        if not os.path.exists(granule_path):
            print(f"Warning: GRANULE path does not exist in {safe_folder}")
            return None
        for d in os.listdir(granule_path):
            img_data = os.path.join(granule_path, d, "IMG_DATA")
            if os.path.exists(img_data):
                return img_data
    except Exception as e:
        print(f"Error while accessing image data path in {safe_folder}: {e}")
    return None


def read_centroid_patch(img_data_path, cx, cy, size=PATCH_SIZE):
    try:
        half = size // 2
        xmin = max(int(cx - half), 0)
        ymin = max(int(cy - half), 0)

        band_files = {}
        for f in os.listdir(img_data_path):
            if f.endswith("_B04.jp2"):
                band_files["R"] = os.path.join(img_data_path, f)
            elif f.endswith("_B03.jp2"):
                band_files["G"] = os.path.join(img_data_path, f)
            elif f.endswith("_B02.jp2"):
                band_files["B"] = os.path.join(img_data_path, f)

        if len(band_files) < 3:
            print(f"Error: Missing required bands for {img_data_path}")
            return None

        window = rasterio.windows.Window(xmin, ymin, size, size)
        with rasterio.open(band_files["R"]) as rsrc:
            r = rsrc.read(1, window=window).astype(np.float32)
        with rasterio.open(band_files["G"]) as gsrc:
            g = gsrc.read(1, window=window).astype(np.float32)
        with rasterio.open(band_files["B"]) as bsrc:
            b = bsrc.read(1, window=window).astype(np.float32)

        if r.size == 0 or g.size == 0 or b.size == 0:
            print(f"Error: Empty patch for centroid at ({cx}, {cy})")
            return None

        r_norm = np.clip(r / 10000.0, 0, 1)
        g_norm = np.clip(g / 10000.0, 0, 1)
        b_norm = np.clip(b / 10000.0, 0, 1)
        return np.dstack([r_norm, g_norm, b_norm])

    except Exception as e:
        print(f"Error reading patch from {img_data_path} at ({cx}, {cy}): {e}")
        return None


def save_patch(crop, scene, row_num, conf, output_dir):
    try:
        crop_bgr = crop[..., ::-1]  # Convert RGB to BGR for OpenCV
        save_path = os.path.join(
            output_dir, f"{scene}_patch_row_{row_num}_conf_{conf:.2f}.png"
        )
        cv2.imwrite(save_path, (crop_bgr * 255).astype(np.uint8))
        # print(f"Saved patch to {save_path}")
        return save_path
    except Exception as e:
        print(f"Error saving patch for {scene} at row {row_num}: {e}")
        return None


# Model Setup
test_transform = transforms.Compose(
    [
        transforms.Resize((MODEL_INPUT_SIZE, MODEL_INPUT_SIZE)),
        transforms.ToTensor(),
    ]
)

weights = ConvNeXt_Tiny_Weights.IMAGENET1K_V1
model = convnext_tiny(weights=weights)

# Replace final classifier
if hasattr(model, "classifier") and isinstance(model.classifier, nn.Sequential):
    for i in range(len(model.classifier) - 1, -1, -1):
        if isinstance(model.classifier[i], nn.Linear):
            in_features = model.classifier[i].in_features
            model.classifier[i] = nn.Linear(in_features, 1)
            break
else:
    model.classifier = nn.Linear(768, 1)

# Load trained weights
try:
    checkpoint = torch.load(
        os.path.join("inference", "filter", "cloudmask.pth"), map_location=DEVICE
    )
    if "model_state_dict" in checkpoint:
        model.load_state_dict(checkpoint["model_state_dict"])
    else:
        model.load_state_dict(checkpoint)
    model = model.to(DEVICE)
    model.eval()
    print("Model loaded successfully")
except Exception as e:
    print(f"Error loading model weights: {e}")
    raise


# Model Prediction
def predict_patch(image_path):
    try:
        img = Image.open(image_path).convert("RGB")
        tensor_img = test_transform(img).unsqueeze(0).to(DEVICE)
        with torch.no_grad():
            out = model(tensor_img)
            prob = torch.sigmoid(out).item()
        return prob
    except Exception as e:
        print(f"Error predicting patch at {image_path}: {e}")
        return 0.0


# Main Execution
new_csv_rows = []
with open(CSV_PATH, "r", newline="") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

with ThreadPoolExecutor(max_workers=12) as executor:
    futures = []

    for row_num, row in enumerate(rows):
        scene = row["image_name"]
        xmin = float(row["xmin"])
        ymin = float(row["ymin"])
        xmax = float(row["xmax"])
        ymax = float(row["ymax"])
        orig_conf = float(row["confidence"])

        safe_folder = os.path.join(ROOT_DATA_DIR, scene)
        img_data_path = find_img_data_path(safe_folder)
        if img_data_path is None:
            print(f"IMG_DATA folder not found for scene {scene}")
            continue

        # Compute centroid
        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0

        # Read 32x32 patch
        crop = read_centroid_patch(img_data_path, cx, cy, size=PATCH_SIZE)
        if crop is None:
            print(f"Error: Patch reading failed for {scene} at row {row_num}")
            continue

        # Save patch
        output_dir = os.path.join(CROP_DIR, scene)
        os.makedirs(output_dir, exist_ok=True)
        patch_path = save_patch(crop, scene, row_num, orig_conf, output_dir)
        if patch_path is None:
            continue

        # Submit model inference
        futures.append((row_num, row, patch_path))

    # After all patches saved, run model inference sequentially or in parallel
    for row_num, row, patch_path in futures:
        cloud_conf = predict_patch(patch_path)
        if cloud_conf >= CONF_THRESHOLD:
            # Add to new CSV
            new_row = row.copy()
            new_row["cloud_confidence"] = cloud_conf
            new_csv_rows.append(new_row)

# ============================================================
# Save filtered results to new CSV
# ============================================================
new_csv_path = os.path.join(os.path.dirname(CSV_PATH), "detections_s2.csv")
fieldnames = list(rows[0].keys()) + ["cloud_confidence"]

try:
    with open(new_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(new_csv_rows)
    print(f"Filtered results saved to {new_csv_path}")
except Exception as e:
    print(f"Error saving filtered CSV: {e}")
