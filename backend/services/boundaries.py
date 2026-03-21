"""
Service to download real maritime boundary data (EEZ + Shipping Lanes).

Follows the same pattern as download_landmask():
- Downloads once to MASK_DIR
- Caches on disk
- No database required

Data sources:
  - EEZ: World EEZ boundaries from Marine Regions / VLIZ (~6MB)
  - Shipping Lanes: Global shipping routes from CIA-derived dataset (~1MB)
"""

import os
from shared.config import MASK_DIR

# Robustly find the mask directory (Internal for Docker, Local for Dev)
LANDMASK_PATH = os.getenv("MASK_DIR", "/app/landmask")
if not os.path.exists(LANDMASK_PATH):
    # Fallback to local project data dir if running outside Docker
    LANDMASK_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "mask"))

print(f"[Boundaries] Using data directory: {LANDMASK_PATH}")

import urllib.request

# Global Boundary Files
EEZ_FILE = os.path.join(LANDMASK_PATH, "world_eez.geojson")
SHIPPING_LANES_FILE = os.path.join(LANDMASK_PATH, "shipping_lanes.geojson")

# Download URLs for fallback (Local Dev)
EEZ_URL = "https://github.com/lmirosevic/ReverseGeo/raw/master/lib/reverse_geo/World-EEZ.geojson"
SHIPPING_LANES_URL = "https://raw.githubusercontent.com/newzealandpaul/Shipping-Lanes/main/data/Shipping_Lanes_v1.geojson"

async def ensure_local_boundaries():
    """Download boundaries if they don't exist in the current environment."""
    os.makedirs(LANDMASK_PATH, exist_ok=True)
    
    for filename, url, path in [
        ("EEZ", EEZ_URL, EEZ_FILE),
        ("Shipping Lanes", SHIPPING_LANES_URL, SHIPPING_LANES_FILE)
    ]:
        if not os.path.exists(path):
            print(f"[Boundaries] {filename} missing at {path}. Downloading...")
            try:
                urllib.request.urlretrieve(url, path)
                print(f"[Boundaries] {filename} downloaded successfully.")
            except Exception as e:
                print(f"[Boundaries] Failed to download {filename}: {e}")
