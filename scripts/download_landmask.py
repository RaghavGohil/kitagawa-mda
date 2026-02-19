import os
import zipfile
import requests

# Configuration
GSHHG_BASE_DIR = "../mnt/data/mask"
GSHHG_SHAPE_PATH = os.path.join(
    GSHHG_BASE_DIR,
    "GSHHS_shp",
    "f",
    "GSHHS_f_L1.shp"
)
GSHHG_URL = "http://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip"
GSHHG_ZIP_PATH = os.path.join(GSHHG_BASE_DIR, "gshhg-shp-2.3.7.zip")


def download_and_extract_gshhg():
    """Download and extract GSHHG shapefiles if not already present."""
    if os.path.exists(GSHHG_SHAPE_PATH):
        print(f"{GSHHG_SHAPE_PATH} already exists. Skipping download.")
        return

    os.makedirs(GSHHG_BASE_DIR, exist_ok=True)

    # Download
    print("Downloading GSHHG shapefiles...")
    response = requests.get(GSHHG_URL, stream=True, timeout=60)
    response.raise_for_status()

    with open(GSHHG_ZIP_PATH, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    print("Download completed:", GSHHG_ZIP_PATH)

    # Extract
    print("Extracting shapefiles...")
    with zipfile.ZipFile(GSHHG_ZIP_PATH, "r") as zip_ref:
        zip_ref.extractall(GSHHG_BASE_DIR)

    print("Extraction completed at:", GSHHG_BASE_DIR)

    # Verify the shapefile exists
    if os.path.exists(GSHHG_SHAPE_PATH):
        print("GSHHG shapefile ready at:", GSHHG_SHAPE_PATH)
    else:
        print("Extraction done, but shapefile not found")


if __name__ == "__main__":
    download_and_extract_gshhg()
