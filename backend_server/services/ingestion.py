"""
Data ingestion service.

Handles downloading satellite images from Copernicus and AIS data from NOAA,
then inserting AIS records into PostGIS.
"""

from __future__ import annotations

import os
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm

from shared.config import (
    AIS_DIR,
    COPERNICUS_PASSWORD,
    COPERNICUS_USERNAME,
    IMAGES_DIR,
    MASK_DIR,
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
        with open(temp_path, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=os.path.basename(temp_path)
        ) as bar:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))


def download_images(image_names: list[str]) -> list[str]:
    """
    Download satellite images from Copernicus Dataspace.
    Returns list of extracted folder paths.
    """
    os.makedirs(IMAGES_DIR, exist_ok=True)

    if not COPERNICUS_USERNAME or not COPERNICUS_PASSWORD:
        print("[Ingestion] Copernicus credentials not set, skipping image download")
        return []

    token, expiry = _get_token()
    downloaded: list[str] = []

    for fname in image_names:
        extracted_folder = os.path.join(IMAGES_DIR, fname)
        if os.path.exists(extracted_folder):
            downloaded.append(extracted_folder)
            continue

        zip_path = os.path.join(IMAGES_DIR, f"{fname}.zip")
        temp_path = zip_path + ".part"

        if not os.path.exists(zip_path):
            if datetime.now(timezone.utc) > expiry:
                token, expiry = _get_token()

            prod_id = _search_product(token, fname)
            if not prod_id:
                print(f"[Ingestion] Product not found: {fname}")
                continue

            try:
                _download_product(token, prod_id, temp_path)
                os.rename(temp_path, zip_path)
            except Exception as e:
                print(f"[Ingestion] Download failed for {fname}: {e}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                continue

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(IMAGES_DIR)
            downloaded.append(extracted_folder)
        except Exception as e:
            print(f"[Ingestion] Extraction failed for {zip_path}: {e}")
            if os.path.exists(extracted_folder):
                import shutil
                shutil.rmtree(extracted_folder)
            if os.path.exists(zip_path):
                os.remove(zip_path)

    return downloaded


def search_recent_images(instrument: str = "SAR", days: int = 7, start_date: str = None, end_date: str = None) -> list[dict]:
    """
    Search for products on Copernicus Dataspace.
    instrument: 'SAR' (Sentinel-1) or 'EO' (Sentinel-2)
    """
    if not COPERNICUS_USERNAME or not COPERNICUS_PASSWORD:
        return []

    token, _ = _get_token()
    
    # Sentinel-1 specific or Sentinel-2 specific
    if instrument == "SAR":
        collection = "SENTINEL-1"
        # Search for IW GRDH products (best for vessel detection)
        specific_filter = "contains(Name, 'IW_GRDH')"
    else:
        collection = "SENTINEL-2"
        specific_filter = "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq 'S2MSI1C')"

    # Date filtering
    if start_date and end_date:
        date_filter = f"ContentDate/Start gt {start_date} and ContentDate/Start lt {end_date}"
    elif start_date:
        date_filter = f"ContentDate/Start gt {start_date}"
    else:
        # Synced to Jan 2, 2025 to match available US AIS data for testing
        date_str = "2025-01-02T00:00:00.000Z"
        date_filter = f"ContentDate/Start gt {date_str}"
    
    print(f"[Ingestion] Searching {collection} ({instrument}) with filter: {date_filter}")
    
    # Build OData filter
    filter_expr = (
        f"Collection/Name eq '{collection}' and "
        f"{specific_filter} and "
        f"{date_filter}"
    )

    # Use Long Beach/LA area as default AOI for testing (matches US AIS data)
    # Bounding Box approx: [-118.5, 33.5, -117.8, 34.0]
    us_aoi = "POLYGON ((-118.5 33.5, -117.8 33.5, -117.8 34.0, -118.5 34.0, -118.5 33.5))"
    spatial_filter = f"OData.CSC.Intersects(area=geography'SRID=4326;{us_aoi}')"
    filter_expr += f" and {spatial_filter}"
    
    params = {
        "$filter": filter_expr,
        "$top": "50",
        "$orderby": "ContentDate/Start asc"
    }

    try:
        r = requests.get(
            CATALOG_ODATA,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30
        )
        r.raise_for_status()
        results = r.json().get("value", [])

        print(f"[Ingestion] Found {len(results)} {instrument} products on CDSE.")
        for res in results[:3]:
            print(f"  - Product: {res['Name']} ({res['ContentDate']['Start']})")
        
        products = []
        for res in results:
            products.append({
                "id": res["Id"],
                "name": res["Name"],
                "timestamp": res["ContentDate"]["Start"],
                "size_gb": round(res["ContentLength"] / (1024**3), 2) if res.get("ContentLength") else 0,
            })
        return products
    except Exception as e:
        print(f"[Ingestion] Search failed for {collection}: {e}")
        return []


# ===================================================================
# AIS data download (NOAA) + PostGIS insert
# ===================================================================
def _extract_dates_from_filenames(
    image_names: list[str],
) -> dict[int, list[tuple[str, str]]]:
    """Extract dates from SAFE filenames, grouped by year."""
    dates_by_year: dict[int, list[tuple[str, str]]] = {}
    for filename in image_names:
        match = re.search(r"(\d{8})T\d{6}", filename)
        if not match:
            continue
        yyyymmdd = match.group(1)
        year = int(yyyymmdd[:4])
        if year <= 2024:
            date_fmt = f"{yyyymmdd[:4]}_{yyyymmdd[4:6]}_{yyyymmdd[6:]}"
            csv_name = f"AIS_{date_fmt}.csv"
        else:
            date_fmt = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
            csv_name = f"ais-{date_fmt}.csv"
        dates_by_year.setdefault(year, []).append((date_fmt, csv_name))
    return dates_by_year


async def download_and_ingest_ais(
    image_names: list[str],
    db: AsyncSession,
    chunk_size: int = 50_000,
) -> int:
    """
    Download AIS CSV files from NOAA and insert into PostGIS.
    Returns total number of records inserted.
    """
    os.makedirs(AIS_DIR, exist_ok=True)

    dates_by_year = _extract_dates_from_filenames(image_names)
    total_inserted = 0

    for year, year_dates in dates_by_year.items():
        base_url = f"https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/index.html"
        try:
            resp = requests.get(base_url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            links = [a["href"] for a in soup.find_all("a", href=True)]
            base_prefix = base_url.rsplit("/", 1)[0]
        except Exception as e:
            print(f"[Ingestion] Failed to fetch AIS index for {year}: {e}")
            continue

        for date_fmt, csv_name in year_dates:
            csv_path = os.path.join(AIS_DIR, csv_name)

            if not os.path.exists(csv_path):
                # Download
                if year <= 2024:
                    archive_name = f"AIS_{date_fmt}.zip"
                else:
                    archive_name = f"ais-{date_fmt}.csv.zst"

                archive_path = os.path.join(AIS_DIR, archive_name)
                if not os.path.exists(archive_path):
                    file_link = None
                    for link in links:
                        if link.lower() == archive_name.lower():
                            file_link = (
                                link
                                if link.startswith("http")
                                else f"{base_prefix}/{link}"
                            )
                            break
                    if not file_link:
                        continue

                    try:
                        temp_path = archive_path + ".part"
                        with requests.get(file_link, stream=True, timeout=300) as r:
                            r.raise_for_status()
                            total = int(r.headers.get("content-length", 0))
                            with open(temp_path, "wb") as f, tqdm(
                                total=total,
                                unit="B",
                                unit_scale=True,
                                desc=archive_name,
                            ) as bar:
                                for chunk in r.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                                        bar.update(len(chunk))
                        os.rename(temp_path, archive_path)
                    except Exception as e:
                        print(f"[Ingestion] AIS download failed: {archive_name}: {e}")
                        continue

                # Extract
                if archive_path.endswith(".zip"):
                    try:
                        with zipfile.ZipFile(archive_path, "r") as zf:
                            zf.extractall(AIS_DIR)
                    except Exception as e:
                        print(f"[Ingestion] AIS extraction failed: {e}")
                        continue
                elif archive_path.endswith(".zst"):
                    try:
                        import zstandard as zstd

                        with open(archive_path, "rb") as comp, open(
                            csv_path, "wb"
                        ) as decomp:
                            dctx = zstd.ZstdDecompressor()
                            with dctx.stream_reader(comp) as reader:
                                for chunk in iter(lambda: reader.read(16384), b""):
                                    decomp.write(chunk)
                    except Exception as e:
                        print(f"[Ingestion] ZST decompression failed: {e}")
                        continue

            # Insert into PostGIS
            if os.path.exists(csv_path):
                count = await _insert_ais_csv(csv_path, db, chunk_size)
                total_inserted += count

    return total_inserted


async def _insert_ais_csv(
    csv_path: str, db: AsyncSession, chunk_size: int
) -> int:
    """Read an AIS CSV and insert records into the ais_tracks table."""
    inserted = 0

    try:
        for chunk in pd.read_csv(csv_path, chunksize=chunk_size):
            chunk.columns = [c.strip().lower() for c in chunk.columns]

            required = {"base_date_time", "latitude", "longitude", "mmsi"}
            if not required.issubset(chunk.columns):
                continue

            chunk["base_date_time"] = pd.to_datetime(
                chunk["base_date_time"], format="%Y-%m-%d %H:%M:%S",
                errors="coerce", utc=True,
            )
            chunk = chunk.dropna(subset=["base_date_time", "latitude", "longitude", "mmsi"])
            if chunk.empty:
                continue

            # Batch insert using secure parameter binding
            batch_data = []
            for _, row in chunk.iterrows():
                batch_data.append({
                    "mmsi": int(row["mmsi"]),
                    "ts": row["base_date_time"].to_pydatetime(),
                    "sog": float(row.get("sog", 0) or 0),
                    "cog": float(row.get("cog", 0) or 0),
                    "lon": float(row["longitude"]),
                    "lat": float(row["latitude"]),
                })

            if batch_data:
                # Insert in sub-batches to avoid oversized queries
                for i in range(0, len(batch_data), 5000):
                    sub_batch = batch_data[i : i + 5000]
                    # We use a single multi-row insert with proper parameter binding
                    # Note: For asyncpg + sqlalchemy, passing a list of dicts to execute() 
                    # is the standard way to do executemany.
                    await db.execute(
                        text("""
                            INSERT INTO ais_tracks (mmsi, timestamp, sog, cog, geom)
                            VALUES (:mmsi, :ts, :sog, :cog, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
                            ON CONFLICT (mmsi, timestamp) DO NOTHING
                        """),
                        sub_batch
                    )
                    await db.commit()
                    inserted += len(sub_batch)

    except Exception as e:
        await db.rollback()
        print(f"[Ingestion] Failed to insert AIS data from {csv_path}: {e}")

    print(f"[Ingestion] Inserted {inserted} AIS records from {os.path.basename(csv_path)}")
    return inserted


# ===================================================================
# Landmask download
# ===================================================================
GSHHG_URL = "http://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip"


def download_landmask():
    """Download and extract GSHHG shapefiles if not already present."""
    shp_path = os.path.join(MASK_DIR, "GSHHS_shp", "f", "GSHHS_f_L1.shp")
    if os.path.exists(shp_path):
        return

    os.makedirs(MASK_DIR, exist_ok=True)
    zip_path = os.path.join(MASK_DIR, "gshhg-shp-2.3.7.zip")

    if not os.path.exists(zip_path):
        print("[Ingestion] Downloading GSHHG shapefiles...")
        response = requests.get(GSHHG_URL, stream=True, timeout=60)
        response.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(MASK_DIR)

    print(f"[Ingestion] Landmask ready at {shp_path}")
