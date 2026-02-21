"""
Lightweight ingestion service for the inference server.
Handles downloading images from Copernicus.
"""

from __future__ import annotations

import os
import requests
import zipfile
import shutil
from datetime import datetime, timedelta, timezone
from typing import Optional
from tqdm import tqdm

class ProgressTracker:
    def __init__(self):
        self.current_progress = 0.0
        self.current_message = "Idle"

    def update(self, progress: float, message: str):
        self.current_progress = progress
        self.current_message = message

    def get_status(self):
        return {"progress": self.current_progress, "message": self.current_message}

# Singleton tracker
progress_tracker = ProgressTracker()

from shared.config import (
    COPERNICUS_PASSWORD,
    COPERNICUS_USERNAME,
    IMAGES_DIR,
)

# ===================================================================
# Image download (Copernicus Dataspace)
# ===================================================================
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/"
    "CDSE/protocol/openid-connect/token"
)
CATALOG_ODATA = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
DOWNLOAD_BASE = "https://download.dataspace.copernicus.eu/odata/v1/Products"


def _get_token() -> tuple[str, datetime]:
    data = {
        "client_id": "cdse-public",
        "grant_type": "password",
        "username": COPERNICUS_USERNAME,
        "password": COPERNICUS_PASSWORD,
    }
    # Log credentials status (masked)
    user_masked = f"{COPERNICUS_USERNAME[:3]}***" if COPERNICUS_USERNAME else "MISSING"
    print(f"[CDSE] Attempting to get token for user: {user_masked}")

    r = requests.post(TOKEN_URL, data=data)
    if r.status_code != 200:
        print(f"[CDSE] Token request failed ({r.status_code}): {r.text}")
        r.raise_for_status()

    js = r.json()
    token = js["access_token"]
    expires_in = int(js["expires_in"])
    return token, datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)


def _search_product(token: str, filename: str) -> Optional[str]:
    params = {"$filter": f"Name eq '{filename}'", "$top": "1"}
    r = requests.get(
        CATALOG_ODATA,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )
    r.raise_for_status()
    val = r.json().get("value", [])
    return val[0]["Id"] if val else None


def _download_product(token: str, product_id: str, temp_path: str):
    url = f"{DOWNLOAD_BASE}({product_id})/$value"
    with requests.get(
        url, headers={"Authorization": f"Bearer {token}"}, stream=True
    ) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(temp_path, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=os.path.basename(temp_path)
        ) as bar:
            for chunk in r.iter_content(chunk_size=81920): # Larger chunks for efficiency
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    bar.update(len(chunk))
                    if total > 0:
                        pct = (downloaded / total) * 100
                        progress_tracker.update(pct, f"Downloading: {pct:.1f}%")

def download_single_image(image_name: str) -> Optional[str]:
    """
    Download and extract a single satellite image.
    Returns the extracted folder path if successful, else None.
    """
    progress_tracker.update(0.0, "Starting download...")
    os.makedirs(IMAGES_DIR, exist_ok=True)

    if not COPERNICUS_USERNAME or not COPERNICUS_PASSWORD:
        print("[Ingestion] Copernicus credentials not set, skipping image download")
        return None

    extracted_folder = os.path.join(IMAGES_DIR, image_name)
    if os.path.exists(extracted_folder):
        return extracted_folder

    zip_path = os.path.join(IMAGES_DIR, f"{image_name}.zip")
    temp_path = zip_path + ".part"

    try:
        token, _ = _get_token()
        prod_id = _search_product(token, image_name)
        if not prod_id:
            print(f"[Ingestion] Product not found: {image_name}")
            return None

        _download_product(token, prod_id, temp_path)
        os.rename(temp_path, zip_path)

        progress_tracker.update(100.0, "Extracting imagery...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(IMAGES_DIR)
        
        # Cleanup zip after extraction
        if os.path.exists(zip_path):
            os.remove(zip_path)
            
        return extracted_folder

    except Exception as e:
        print(f"[Ingestion] Failed to download {image_name}: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(extracted_folder):
            shutil.rmtree(extracted_folder)
        return None
