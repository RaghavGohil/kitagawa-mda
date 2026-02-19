import os
import requests
import zipfile
from datetime import datetime, timedelta, timezone
from tqdm import tqdm

USERNAME = os.getenv("COPERNICUS_USERNAME")
PASSWORD = os.getenv("COPERNICUS_PASSWORD")

if not USERNAME or not PASSWORD:
    raise RuntimeError("Please set environment vars.")

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/" \
    "CDSE/protocol/openid-connect/token"
CATALOG_ODATA = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
DOWNLOAD_BASE = "https://download.dataspace.copernicus.eu/odata/v1/Products"


def get_token():
    data = {
        "client_id": "cdse-public",
        "grant_type": "password",
        "username": USERNAME,
        "password": PASSWORD,
    }
    r = requests.post(TOKEN_URL, data=data)
    r.raise_for_status()
    js = r.json()
    token = js["access_token"]
    expires_in = int(js["expires_in"])
    # Use timezone-aware datetime for UTC now
    return token, datetime.now(timezone.utc) + \
        timedelta(seconds=expires_in - 60)


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def search_product(token, filename):
    params = {"$filter": f"Name eq '{filename}'", "$top": "1"}
    r = requests.get(CATALOG_ODATA, headers=headers(token), params=params)
    r.raise_for_status()
    val = r.json().get("value", [])
    if val:
        return val[0]["Id"]
    return None


def download_product(token, product_id, temp_path):
    url = f"{DOWNLOAD_BASE}({product_id})/$value"
    with requests.get(url, headers=headers(token), stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get('content-length', 0))
        with open(temp_path, "wb") as f, tqdm(
            total=total, unit='B',
            unit_scale=True,
            desc=os.path.basename(temp_path)
        ) as bar:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))


def extract_zip(zip_path, extract_dir):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)
    print(f"Extracted {zip_path} to {extract_dir}")


token, expiry = get_token()
filenames_file = "../mnt/data/vessel_detection_image_names.txt"
output_dir = "../mnt/data/inference_images"
os.makedirs(output_dir, exist_ok=True)

with open(filenames_file) as f:
    filenames = [line.strip() for line in f if line.strip()]

for fname in filenames:
    temp_path = os.path.join(output_dir, f"{fname}.zip.part")
    final_zip_path = os.path.join(output_dir, f"{fname}.zip")

    extracted_folder_path = os.path.join(output_dir, fname)
    if os.path.exists(extracted_folder_path):
        print(f"Skipping already extracted: {fname}")
        continue

    if not os.path.exists(final_zip_path):
        if datetime.now(timezone.utc) > expiry:
            token, expiry = get_token()

        print(f"Searching for {fname}...")
        prod_id = search_product(token, fname)
        if not prod_id:
            print(f"Product not found: {fname}")
            continue

        print(f"Downloading {fname}...")
        try:
            download_product(token, prod_id, temp_path)
            os.rename(temp_path, final_zip_path)
            print(f"Saved to {final_zip_path}")
        except Exception as e:
            print(f"Failed downloading {fname}: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            continue
    else:
        print(f"{final_zip_path} already downloaded.")

    try:
        extract_zip(final_zip_path, output_dir)
        # Keep zip after extraction as requested
    except Exception as e:
        print(f"Failed extracting {final_zip_path}: {e}")
