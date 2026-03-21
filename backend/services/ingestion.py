"""
Data ingestion service.

Handles downloading satellite images from Copernicus and AIS data from NOAA,
then inserting AIS records into PostGIS.
"""

from __future__ import annotations

import os
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm
import httpx

from shared.config import (
    AIS_DIR,
    COPERNICUS_PASSWORD,
    COPERNICUS_USERNAME,
    IMAGES_DIR,
    MASK_DIR,
)

# ===================================================================
# Constants & AOIs
# ===================================================================
# US East Coast Offshore (roughly 24N-45N, prioritizing water and avoiding inland)
# Original: US_WATERS_WKT = "POLYGON((-82 24, -65 24, -65 45, -82 45, -82 24))"
US_WATERS_WKT = "POLYGON((-76.0 32.0, -70.0 32.0, -70.0 40.0, -76.0 40.0, -76.0 32.0))"


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


def _download_product(
    token: str, product_id: str, temp_path: str, progress_callback=None
):
    url = f"{DOWNLOAD_BASE}({product_id})/$value"
    with requests.get(
        url, headers={"Authorization": f"Bearer {token}"}, stream=True
    ) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with (
            open(temp_path, "wb") as f,
            tqdm(
                total=total, unit="B", unit_scale=True, desc=os.path.basename(temp_path)
            ) as bar,
        ):
            for chunk in r.iter_content(
                chunk_size=65536
            ):  # Larger chunks for better perf
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    bar.update(len(chunk))
                    if progress_callback and total > 0:
                        progress_callback(round((downloaded / total) * 100, 1))


async def download_images(image_names: list[str], progress_callback=None) -> list[str]:
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
                # Wrap the callback to include file context if needed
                def _cb(pct):
                    if progress_callback:
                        progress_callback(pct, fname)

                import asyncio

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, _download_product, token, prod_id, temp_path, _cb
                )
                os.rename(temp_path, zip_path)
            except Exception as e:
                print(f"[Ingestion] Download failed for {fname}: {e}")
                if "No space left on device" in str(e) or (
                    hasattr(e, "errno") and e.errno == 28
                ):
                    print(
                        f"[Ingestion] CRITICAL: Disk full during download of {fname}. Cleaning up partials."
                    )
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                    # Trigger emergency cleanup (but don't wait/retry here, let next loop handle folder)
                    from backend.db.connection import async_session

                    async with async_session() as db:
                        await cleanup_uncorrelated_ais(db, preserve_days=1)

                # Cleanup partial on any error to prevent corrupted zips
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                continue

        try:

            def _extract():
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(IMAGES_DIR)

            await loop.run_in_executor(None, _extract)
            downloaded.append(extracted_folder)
        except Exception as e:
            print(f"[Ingestion] Extraction failed for {zip_path}: {e}")
            if "No space left on device" in str(e) or (
                hasattr(e, "errno") and e.errno == 28
            ):
                print(
                    f"[Ingestion] CRITICAL: Disk full during extraction of {fname}. Cleaning up partials and aborting."
                )
                # Trigger emergency cleanup
                from backend.db.connection import async_session

                async with async_session() as db:
                    await cleanup_uncorrelated_ais(db, preserve_days=1)

            # Cleanup broken extraction AND the zip file so it can be retried cleanly later
            if os.path.exists(extracted_folder):
                import shutil

                shutil.rmtree(extracted_folder, ignore_errors=True)
            if os.path.exists(zip_path):
                os.remove(zip_path)

    return downloaded


async def search_recent_images(
    instrument: str = "SAR",
    days: int = 7,
    limit: int = 100,
    start_date: str = None,
    end_date: str = None,
    aoi: str = None,
) -> tuple[list[dict], str]:
    """
    Search CDSE OData for recent Sentinel products.
    Returns (list of products, filter_expression used).
    """
    if not COPERNICUS_USERNAME or not COPERNICUS_PASSWORD:
        return [], ""

    token, _ = _get_token()

    if start_date and end_date:
        t_start = start_date
        t_end = end_date
    else:
        now = datetime.now(timezone.utc)
        t_start = (now - timedelta(days=days)).isoformat().replace("+00:00", "") + "Z"
        t_end = now.isoformat().replace("+00:00", "") + "Z"

    # Sentinel-1 (SAR) or Sentinel-2 (EO)
    collection = "SENTINEL-1" if instrument == "SAR" else "SENTINEL-2"

    specific_filter = ""
    if instrument == "SAR":
        # Search for IW GRDH products (best for vessel detection)
        specific_filter = "contains(Name,'IW_GRDH')"
    else:
        # Sentinel-2 L1C products
        specific_filter = "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq 'S2MSI1C')"

    # Date filter
    date_filter = f"ContentDate/Start gt {t_start} and ContentDate/Start lt {t_end}"

    # Build OData filter
    filter_expr = f"Collection/Name eq '{collection}' and {date_filter}"
    if specific_filter:
        filter_expr += f" and {specific_filter}"

    if aoi:
        # Add spatial filter if AOI provided
        filter_expr += f" and OData.CSC.Intersects(area=geography'SRID=4326;{aoi}')"

    print(
        f"[Ingestion] Searching {collection} ({instrument}) with filter: {filter_expr}"
    )

    url = f"{CATALOG_ODATA}?$filter={filter_expr}&$top={limit}&$orderby=ContentDate/Start desc"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("value", []):
                results.append(
                    {
                        "id": item["Id"],
                        "name": item["Name"],
                        "timestamp": item["ContentDate"]["Start"],
                        "size": item["ContentLength"],
                    }
                )
            print(f"[Ingestion] Found {len(results)} {instrument} products.")
            return results, filter_expr
    except Exception as e:
        print(f"[Ingestion] CDSE search failed: {e}")
        return [], filter_expr


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
    Records AIS coverage per date for the 4-state classification.
    Returns total number of records inserted.
    """
    os.makedirs(AIS_DIR, exist_ok=True)

    dates_by_year = _extract_dates_from_filenames(image_names)
    total_inserted = 0

    for year, year_dates in dates_by_year.items():
        try:
            # Use the year from the loop, but if it's the current year, use the dynamic index
            index_url = (
                f"https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/index.html"
            )
            print(f"[Ingestion] Fetching AIS index from {index_url}...")

            import asyncio

            loop = asyncio.get_event_loop()

            def _get_index():
                return requests.get(index_url, timeout=15)

            resp = await loop.run_in_executor(None, _get_index)
            resp.raise_for_status()

            # Parse HTML for links
            soup = BeautifulSoup(resp.text, "html.parser")
            links = [a["href"] for a in soup.find_all("a", href=True)]
            base_prefix = index_url.rsplit("/", 1)[0]
        except Exception as e:
            print(
                f"[Ingestion] skipping NOAA AIS fetch for {year} (likely no coverage or too recent): {e}"
            )
            # Mark ALL dates for this year as no-coverage UNLESS it's the current year
            # (where we might have live data instead of NOAA files)
            current_year = datetime.now().year
            if str(year) != str(current_year):
                for d_tuple in year_dates:
                    await _record_ais_coverage(db, d_tuple[0], has_coverage=False)
            continue

        for d_tuple in year_dates:
            date_fmt = d_tuple[0]

            # Check if already processed
            already = await check_ais_coverage(db, date_fmt)
            if already is not None:
                continue

            # NOAA format: AISVesselTracksYYYY.zip or AISVesselTracksYYYY.zst
            # They seem to provide daily/monthly files depending on recency. For 2024/2025,
            # they often provide daily files like AIS_YYYY_MM_DD.zip or yearly blocks.
            # We look for AIS_YYYY_MM_DD.zip or just the yearly zip.
            parts = date_fmt.replace("_", "-").split("-")
            year_str, mm_str, dd_str = parts[0], parts[1], parts[2]

            # Possible filenames NOAA uses:
            possible_names = [
                f"AIS_{year_str}_{mm_str}_{dd_str}.zip",
                f"AIS_ASCII_by_UTM_Month_{year_str}_{mm_str}.zip",
                f"AISVesselTracks{year_str}.zip",
                f"AISVesselTracks{year_str}.zst",
            ]

            file_link = None
            archive_name = None
            for plink in possible_names:
                for link in links:
                    if link.lower() == plink.lower():
                        file_link = f"{base_prefix}/{link}"
                        archive_name = link
                        break
                if file_link:
                    break

            if not file_link:
                print(
                    f"[Ingestion] No matching AIS file found for {date_fmt} at {index_url}"
                )
                await _record_ais_coverage(db, date_fmt, has_coverage=False)
                continue

            archive_path = os.path.join(AIS_DIR, archive_name)

            if not os.path.exists(archive_path):
                print(
                    f"[Ingestion] Downloading matching NOAA AIS file: {file_link} ..."
                )
                temp_path = archive_path + ".part"
                try:
                    with requests.get(file_link, stream=True, timeout=300) as r:
                        r.raise_for_status()
                        total = int(r.headers.get("content-length", 0))
                        with (
                            open(temp_path, "wb") as f,
                            tqdm(
                                total=total,
                                unit="B",
                                unit_scale=True,
                                desc=archive_name,
                            ) as bar,
                        ):
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    bar.update(len(chunk))
                    os.rename(temp_path, archive_path)
                except Exception as e:
                    print(f"[Ingestion] AIS download failed: {archive_name}: {e}")
                    await _record_ais_coverage(db, date_fmt, has_coverage=False)
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                    if "No space left on device" in str(e) or (
                        hasattr(e, "errno") and e.errno == 28
                    ):
                        print(
                            f"[Ingestion] CRITICAL: Disk full during AIS download of {archive_name}. Cleaning up."
                        )
                        await cleanup_uncorrelated_ais(db, preserve_days=1)

                    continue

                # Extract
                csv_name = f"AIS_{date_fmt}.csv"
                csv_path = os.path.join(AIS_DIR, csv_name)

                if archive_path.endswith(".zip"):
                    try:

                        def _ext_zip():
                            with zipfile.ZipFile(archive_path, "r") as zf:
                                zf.extractall(AIS_DIR)

                        await loop.run_in_executor(None, _ext_zip)
                    except Exception as e:
                        print(f"[Ingestion] AIS extraction failed: {e}")
                elif archive_path.endswith(".zst"):
                    try:
                        import zstandard as zstd

                        def _ext_zstd(in_file, out_file):
                            with (
                                open(in_file, "rb") as comp,
                                open(out_file, "wb") as decomp,
                            ):
                                dctx = zstd.ZstdDecompressor()
                                with dctx.stream_reader(comp) as reader:
                                    for chunk in iter(lambda: reader.read(16384), b""):
                                        decomp.write(chunk)

                        await loop.run_in_executor(
                            None, _ext_zstd, archive_path, csv_path
                        )
                    except Exception as e:
                        print(f"[Ingestion] ZST decompression failed: {e}")
                        await _record_ais_coverage(db, date_fmt, has_coverage=False)
                        continue
            if not os.path.exists(csv_path):
                # Check for extracted files with dynamic names from NOAA zips
                dynamic_csv = os.path.join(
                    AIS_DIR, f"AIS_{year_str}_{mm_str}_{dd_str}.csv"
                )
                if os.path.exists(dynamic_csv):
                    os.rename(dynamic_csv, csv_path)
                else:
                    print(
                        f"[Ingestion] Warning: {csv_path} not found after extraction."
                    )
                    await _record_ais_coverage(db, date_fmt, has_coverage=False)
                    continue

            # Insert into PostGIS
            if os.path.exists(csv_path):
                print(f"[Ingestion] Inserting AIS data from {csv_path} ...")
                try:
                    count = await _insert_ais_csv(csv_path, db, chunk_size)
                    total_inserted += count
                    # Mark coverage as TRUE if any data was inserted
                    await _record_ais_coverage(db, date_fmt, has_coverage=(count > 0))
                except Exception as e:
                    print(f"[Ingestion] Failed to insert {csv_path}: {e}")
                    # Only mark as no coverage if we are sure (e.g. not a transient DB error)
                    if "No space left on device" in str(e):
                        await _record_ais_coverage(db, date_fmt, has_coverage=False)
                    continue
            else:
                print(
                    f"[Ingestion] Expected CSV {csv_path} not found after extraction."
                )
                await _record_ais_coverage(db, date_fmt, has_coverage=False)

    return total_inserted


async def check_ais_coverage(db: AsyncSession, date_fmt: str) -> bool | None:
    """Check if we already attempted to download AIS data for this date."""
    try:
        clean = date_fmt.replace("_", "-")
        date_val = datetime.strptime(clean, "%Y-%m-%d").date()
        result = await db.execute(
            text("SELECT has_coverage FROM ais_coverage_dates WHERE date = :d"),
            {"d": date_val},
        )
        row = result.fetchone()
        if row is not None:
            return bool(row[0])
    except Exception as e:
        print(f"[Ingestion] Error checking AIS coverage: {e}")
    return None


async def _record_ais_coverage(db: AsyncSession, date_fmt: str, has_coverage: bool):
    """Record whether AIS data is available for a given date."""
    try:
        # Parse date from format like "2025-01-02" or "2025_01_02"
        clean = date_fmt.replace("_", "-")
        date_val = datetime.strptime(clean, "%Y-%m-%d").date()
        coverage_int = 1 if has_coverage else 0
        await db.execute(
            text("""
                INSERT INTO ais_coverage_dates (date, has_coverage, checked_at)
                VALUES (:d, :cov, NOW())
                ON CONFLICT (date) DO UPDATE SET
                    has_coverage = GREATEST(ais_coverage_dates.has_coverage, :cov),
                    checked_at = NOW()
            """),
            {"d": date_val, "cov": coverage_int},
        )
        await db.commit()
        print(
            f"[Ingestion] AIS coverage for {date_val}: {'YES' if has_coverage else 'NO'}"
        )
    except Exception as e:
        print(f"[Ingestion] Failed to record AIS coverage for {date_fmt}: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


async def _insert_ais_csv(csv_path: str, db: AsyncSession, chunk_size: int) -> int:
    """Read an AIS CSV and insert records into the ais_tracks table."""
    inserted = 0

    try:
        import asyncio

        loop = asyncio.get_event_loop()

        # Read CSV is blocking, move it to executor or at least chunk processing
        # Since pd.read_csv with chunksize is an iterator, we need to be careful.
        # We will wrap the entire iteration or the processing of each chunk.

        def _get_chunks():
            return pd.read_csv(csv_path, chunksize=chunk_size)

        chunks = await loop.run_in_executor(None, _get_chunks)

        for chunk in chunks:

            def _process_chunk(df):
                df.columns = [c.strip().lower() for c in df.columns]

                required = {"base_date_time", "latitude", "longitude", "mmsi"}
                if not required.issubset(df.columns):
                    return None, None

                df["base_date_time"] = pd.to_datetime(
                    df["base_date_time"],
                    format="%Y-%m-%d %H:%M:%S",
                    errors="coerce",
                    utc=True,
                )
                df = df.dropna(
                    subset=["base_date_time", "latitude", "longitude", "mmsi"]
                )

                # SPATIAL FILTER (Default to global if not set)
                min_lon = float(os.getenv("AIS_MIN_LON", "-180.0"))
                max_lon = float(os.getenv("AIS_MAX_LON", "180.0"))
                min_lat = float(os.getenv("AIS_MIN_LAT", "-90.0"))
                max_lat = float(os.getenv("AIS_MAX_LAT", "90.0"))

                df = df[
                    (df["longitude"] >= min_lon)
                    & (df["longitude"] <= max_lon)
                    & (df["latitude"] >= min_lat)
                    & (df["latitude"] <= max_lat)
                ]

                if df.empty:
                    return [], {}

                batch_data = []
                vessel_batch_data = {}
                for _, row in df.iterrows():
                    mmsi_val = int(row["mmsi"])
                    batch_data.append(
                        {
                            "mmsi": mmsi_val,
                            "ts": row["base_date_time"].to_pydatetime(),
                            "sog": float(row.get("sog", 0) or 0),
                            "cog": float(row.get("cog", 0) or 0),
                            "lon": float(row["longitude"]),
                            "lat": float(row["latitude"]),
                        }
                    )

                    if "vessel_name" in row and pd.notna(row["vessel_name"]):
                        vname = str(row["vessel_name"]).strip()
                        if vname:
                            vtype = (
                                str(row.get("vessel_type", "")).strip()
                                if pd.notna(row.get("vessel_type", ""))
                                else None
                            )
                            vessel_batch_data[mmsi_val] = {
                                "mmsi": mmsi_val,
                                "vname": vname[:512],
                                "vtype": vtype[:255] if vtype else None,
                            }
                return batch_data, vessel_batch_data

            batch_data, vessel_batch_data = await loop.run_in_executor(
                None, _process_chunk, chunk
            )

            if batch_data is None:
                continue

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
                        sub_batch,
                    )
                    await db.commit()
                    inserted += len(sub_batch)

            if vessel_batch_data:
                vessels_list = list(vessel_batch_data.values())
                for i in range(0, len(vessels_list), 5000):
                    sub_vessels = vessels_list[i : i + 5000]
                    await db.execute(
                        text("""
                            INSERT INTO ais_vessels (mmsi, vessel_name, vessel_type)
                            VALUES (:mmsi, :vname, :vtype)
                            ON CONFLICT (mmsi) DO UPDATE SET
                                vessel_name = COALESCE(EXCLUDED.vessel_name, ais_vessels.vessel_name),
                                vessel_type = COALESCE(EXCLUDED.vessel_type, ais_vessels.vessel_type)
                        """),
                        sub_vessels,
                    )
                    await db.commit()

    except Exception as e:
        await db.rollback()
        # Check for PostgreSQL Disk Full error (53100)
        if (
            hasattr(e, "orig")
            and hasattr(e.orig, "sqlstate")
            and e.orig.sqlstate == "53100"
        ):
            print(
                "[Ingestion] DISK FULL detected in Database! Triggering emergency AIS cleanup..."
            )
            await cleanup_uncorrelated_ais(db)
            # We don't retry here to avoid loops, but next chunk might succeed after cleanup
        else:
            print(f"[Ingestion] Failed to insert AIS data from {csv_path}: {e}")

    print(
        f"[Ingestion] Inserted {inserted} AIS records from {os.path.basename(csv_path)}"
    )
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


async def cleanup_uncorrelated_ais(db: AsyncSession, preserve_days: int = 3):
    """
    Delete AIS tracks that do not correspond to any detected vessel's MMSI,
    but preserve very recent data (default 3 days) to allow for correlation.
    """
    print(
        f"[Ingestion] Running AIS track cleanup (preserving last {preserve_days} days)..."
    )
    try:
        # 1. Identify all MMSIs that have a detection
        # 2. Delete tracks for MMSIs not in the list AND older than preserve_days
        threshold = datetime.now(timezone.utc) - timedelta(days=preserve_days)

        await db.execute(
            text("""
                DELETE FROM ais_tracks 
                WHERE mmsi NOT IN (SELECT DISTINCT mmsi FROM detections WHERE mmsi IS NOT NULL)
                  AND timestamp < :threshold
            """),
            {"threshold": threshold},
        )

        await db.commit()
        print("[Ingestion] AIS cleanup complete.")
    except Exception as e:
        await db.rollback()
        print(f"[Ingestion] AIS cleanup failed: {e}")
