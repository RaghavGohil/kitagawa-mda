"""
Image chip generation and MinIO storage service.

Crops detection bounding boxes from source images and uploads
them to MinIO for fast frontend consumption via pre-signed URLs.
"""

from __future__ import annotations

import io
import os
from datetime import timedelta
from typing import Optional, Callable, Awaitable

import numpy as np
from minio import Minio
from minio.error import S3Error
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import (
    IMAGES_DIR,
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
)


# ---------------------------------------------------------------------------
# MinIO client singleton
# ---------------------------------------------------------------------------
_minio_client: Optional[Minio] = None


def get_minio_client() -> Minio:
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
        # Ensure bucket exists
        if not _minio_client.bucket_exists(MINIO_BUCKET):
            _minio_client.make_bucket(MINIO_BUCKET)
            print(f"[Chips] Created MinIO bucket: {MINIO_BUCKET}")
    return _minio_client


# Chip generation
# ---------------------------------------------------------------------------
async def generate_and_upload_chips(
    db: AsyncSession,
    image_name: Optional[str] = None,
    progress_callback: Optional[Callable[[float], Awaitable[None]]] = None,
) -> int:
    """
    For all detections without an image chip, crop the detection area
    from the source image and upload to MinIO.

    Returns number of chips created.
    """
    import asyncio
    import cv2

    # Early exit: if image_name given, verify folder exists on disk first
    if image_name:
        safe_folder = os.path.join(IMAGES_DIR, image_name)
        if not os.path.isdir(safe_folder):
            print(f"[Chips] Skipping: image folder not on disk at {safe_folder}")
            return 0

    client = get_minio_client()

    # Find detections without chips
    sql_base = """
            SELECT d.id, d.image_name, d.sensor_type,
                   d.bbox_xmin, d.bbox_ymin, d.bbox_xmax, d.bbox_ymax,
                   ST_Y(d.geom) AS lat, ST_X(d.geom) AS lon
            FROM detections d
            LEFT JOIN image_chips ic ON ic.detection_id = d.id
            WHERE ic.id IS NULL
    """
    params = {}
    if image_name:
        sql_base += " AND d.image_name = :img"
        params["img"] = image_name

    sql_base += " ORDER BY d.id"

    result = await db.execute(text(sql_base), params)
    rows = result.fetchall()

    if not rows:
        print(
            f"[Chips] No new chips to generate{f' for {image_name}' if image_name else ''}."
        )
        return 0

    print(f"[Chips] Processing {len(rows)} detections for chip generation...")

    created = 0
    skipped = 0
    total_rows = len(rows)
    loop = asyncio.get_event_loop()

    for i, row in enumerate(rows):
        if progress_callback:
            await progress_callback((i + 1) / total_rows * 100.0)

        det_id = row[0]
        det_img_name = row[1]  # Avoid shadowing the function parameter
        sensor_type = row[2]
        xmin, ymin, xmax, ymax = row[3], row[4], row[5], row[6]
        lat, lon = row[7], row[8]

        # Run blocking rasterio I/O in executor with timeout
        try:
            chip = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    _extract_chip,
                    det_img_name,
                    sensor_type,
                    xmin,
                    ymin,
                    xmax,
                    ymax,
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            print(f"[Chips] Timeout extracting chip for detection {det_id}, skipping.")
            skipped += 1
            continue
        except Exception as e:
            print(f"[Chips] Error extracting chip {det_id}: {e}")
            skipped += 1
            continue

        if chip is None:
            skipped += 1
            continue

        # Encode as PNG and Upload to MinIO (Moved to executor)
        try:
            minio_key = f"{sensor_type}/{det_img_name}/{det_id}.png"

            # We bundle these so we only hit the executor once per chip
            def _save_and_upload():
                success, buffer = cv2.imencode(".png", chip)
                if not success:
                    return False

                data = io.BytesIO(buffer.tobytes())
                data_len = len(buffer.tobytes())

                client.put_object(
                    MINIO_BUCKET,
                    minio_key,
                    data,
                    data_len,
                    content_type="image/png",
                )
                return True

            success = await loop.run_in_executor(None, _save_and_upload)
            if not success:
                skipped += 1
                continue
        except S3Error as e:
            print(f"[Chips] MinIO upload failed for {det_id}: {e}")
            skipped += 1
            continue
        except Exception as e:
            print(f"[Chips] Error processing/uploading chip {det_id}: {e}")
            skipped += 1
            continue

        # Insert chip record
        await db.execute(
            text("""
                INSERT INTO image_chips
                    (detection_id, image_name, sensor_type, minio_key, center)
                VALUES
                    (:det_id, :img_name, :sensor, :key,
                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
            """),
            {
                "det_id": det_id,
                "img_name": det_img_name,
                "sensor": sensor_type,
                "key": minio_key,
                "lon": lon,
                "lat": lat,
            },
        )
        created += 1

        # Log progress every 10 chips
        if (i + 1) % 10 == 0:
            print(
                f"[Chips] Progress: {i + 1}/{total_rows} (created={created}, skipped={skipped})"
            )

    await db.commit()
    print(f"[Chips] Done. Generated {created} chips, skipped {skipped}.")
    return created


def get_chip_url(minio_key: str, expires_hours: int = 24) -> str:
    """Generate a pre-signed URL for a chip in MinIO."""
    client = get_minio_client()
    try:
        url = client.presigned_get_object(
            MINIO_BUCKET,
            minio_key,
            expires=timedelta(hours=expires_hours),
        )
        return url
    except S3Error:
        return ""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------
def _extract_chip(
    image_name: str,
    sensor_type: str,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    padding: int = 16,
) -> Optional[np.ndarray]:
    """
    Extract a chip from the source satellite image.
    Returns BGR numpy array or None.
    """
    pass

    safe_folder = os.path.join(IMAGES_DIR, image_name)
    if not os.path.isdir(safe_folder):
        return None

    x1 = max(0, int(xmin) - padding)
    y1 = max(0, int(ymin) - padding)
    w = int(xmax - xmin) + 2 * padding
    h = int(ymax - ymin) + 2 * padding

    try:
        if sensor_type == "SAR":
            return _extract_sar_chip(safe_folder, x1, y1, w, h)
        elif sensor_type == "EO":
            return _extract_eo_chip(safe_folder, x1, y1, w, h)
    except Exception as e:
        print(f"[Chips] Failed to extract chip from {image_name}: {e}")

    return None


def _extract_sar_chip(
    safe_folder: str, x: int, y: int, w: int, h: int
) -> Optional[np.ndarray]:
    """Extract a chip from SAR VV TIFF."""
    import rasterio
    from rasterio.windows import Window

    meas_path = os.path.join(safe_folder, "measurement")
    if not os.path.isdir(meas_path):
        return None

    tiff = next(
        (
            os.path.join(meas_path, f)
            for f in os.listdir(meas_path)
            if f.lower().endswith(".tiff") and "vv" in f.lower()
        ),
        None,
    )
    if not tiff:
        return None

    with rasterio.open(tiff) as src:
        patch = src.read(1, window=Window(x, y, w, h)).astype(np.float32)

    pmin, pmax = float(np.nanmin(patch)), float(np.nanmax(patch))
    if pmax > pmin:
        patch = ((patch - pmin) / (pmax - pmin) * 255).astype(np.uint8)
    else:
        patch = np.zeros_like(patch, dtype=np.uint8)

    return np.stack([patch, patch, patch], axis=-1)  # BGR


def _extract_eo_chip(
    safe_folder: str, x: int, y: int, w: int, h: int
) -> Optional[np.ndarray]:
    """Extract a chip from EO RGB bands."""
    import rasterio
    from rasterio.windows import Window

    granule_path = os.path.join(safe_folder, "GRANULE")
    if not os.path.isdir(granule_path):
        return None

    img_data = None
    for d in os.listdir(granule_path):
        candidate = os.path.join(granule_path, d, "IMG_DATA")
        if os.path.isdir(candidate):
            img_data = candidate
            break

    if not img_data:
        return None

    bands = {}
    for f in os.listdir(img_data):
        for b in ("B04", "B03", "B02"):
            if f.endswith(f"_{b}.jp2"):
                bands[b] = os.path.join(img_data, f)

    if len(bands) < 3:
        return None

    window = Window(x, y, w, h)
    with rasterio.open(bands["B04"]) as src:
        r = src.read(1, window=window).astype(np.float32)
    with rasterio.open(bands["B03"]) as src:
        g = src.read(1, window=window).astype(np.float32)
    with rasterio.open(bands["B02"]) as src:
        b = src.read(1, window=window).astype(np.float32)

    r = (np.clip(r / 10000.0, 0, 1) * 255).astype(np.uint8)
    g = (np.clip(g / 10000.0, 0, 1) * 255).astype(np.uint8)
    b = (np.clip(b / 10000.0, 0, 1) * 255).astype(np.uint8)

    return np.dstack([b, g, r])  # BGR for OpenCV
