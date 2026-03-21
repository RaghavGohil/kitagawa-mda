"""
Pipeline API — triggering data ingestion, inference, and correlation.

Provides endpoints for orchestrating the full data processing pipeline
from the HTTP API instead of requiring CLI/Prefect.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from shared.config import IMAGES_DIR, INFERENCE_SERVER_URL
from shared.schemas import InferenceResponse, PipelineStatus
from shared.utils import check_resources
from backend.db.connection import get_db, async_session
from backend.db.models import ProcessedImage
from backend.services.ingestion import (
    search_recent_images,
    cleanup_uncorrelated_ais,
    US_WATERS_WKT,
)


def parse_iso_datetime(dt_str: str | None) -> datetime | None:
    """Robust ISO 8601 parsing for detection timestamps."""
    if not dt_str:
        return None
    try:
        # Handle trailing Z and other variations
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def cleanup_orphaned_downloads():
    """Remove .part files in IMAGES_DIR that haven't been modified in 2 hours."""
    import os
    import time

    if not os.path.exists(IMAGES_DIR):
        return

    now = time.time()
    for f in os.listdir(IMAGES_DIR):
        if f.endswith(".part"):
            path = os.path.join(IMAGES_DIR, f)
            try:
                if now - os.path.getmtime(path) > 7200:  # 2 hours
                    print(f"[Cleanup] Removing orphaned download: {f}")
                    os.remove(path)
            except Exception as e:
                print(f"[Cleanup] Failed to remove {f}: {e}")


router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])

# Simple in-memory pipeline status tracker
_pipeline_status = PipelineStatus(status="idle")

# Progress tracking helpers
_current_base_total = 0.0
_current_image_weight = 0.0


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                pass


manager = ConnectionManager()


async def broadcast_status():
    """Helper to broadcast current _pipeline_status to all WS clients."""
    from fastapi.encoders import jsonable_encoder

    await manager.broadcast(jsonable_encoder(_pipeline_status))


@router.websocket("/ws")
async def websocket_status(websocket: WebSocket):
    """WebSocket endpoint for real-time pipeline status pushes."""
    await manager.connect(websocket)
    try:
        # Send initial state immediately
        await broadcast_status()
        while True:
            # Wait for any message or disconnect
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        manager.disconnect(websocket)


@router.get("/status", response_model=PipelineStatus)
async def get_pipeline_status():
    """Get the current pipeline status."""
    return _pipeline_status


@router.get("/search")
async def search_copernicus(
    instrument: str = "SAR", days: int = 7, start_date: str = None, end_date: str = None
):
    """Search for available images in Copernicus."""
    results, filter_expr = await search_recent_images(
        instrument, days, start_date=start_date, end_date=end_date, aoi=US_WATERS_WKT
    )
    return {"results": results, "count": len(results), "filter": filter_expr}


@router.post("/run")
async def run_pipeline(
    image_names: list[str],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a full processing pipeline:
    1. Download images (Copernicus)
    2. Download AIS data (NOAA)
    3. Download landmask (GSHHG)
    4. Submit images to inference server
    5. Store detections in PostGIS
    6. Generate image chips → MinIO
    7. Run AIS correlation
    """
    global _pipeline_status
    if _pipeline_status.status == "running":
        raise HTTPException(status_code=409, detail="Pipeline already running")

    _pipeline_status = PipelineStatus(
        status="running",
        progress=0.0,
        message="Starting pipeline...",
        started_at=datetime.now(timezone.utc),
        total_images=len(image_names),
        processed_images=[],
        failed_images=[],
        queued_images=image_names.copy(),
    )

    background_tasks.add_task(_run_pipeline_task, image_names)
    await broadcast_status()
    return {"status": "started", "images": image_names}


@router.post("/reset")
async def reset_pipeline():
    """Manual emergency reset of the pipeline status."""
    global _pipeline_status
    print(
        f"[Pipeline] Manual reset triggered. Previous state: {_pipeline_status.status}"
    )
    _pipeline_status = PipelineStatus(
        status="idle",
        message="Manually reset via API",
        completed_at=datetime.now(timezone.utc),
    )
    await broadcast_status()
    return {"status": "reset", "message": "Pipeline status cleared to idle"}


async def _poll_inference_progress(stop_event: asyncio.Event):
    """Poll inference server's /progress endpoint until stop_event is set."""
    global _current_base_total, _current_image_weight
    async with httpx.AsyncClient(timeout=10) as client:
        while not stop_event.is_set():
            try:
                resp = await client.get(f"{INFERENCE_SERVER_URL}/progress")
                if resp.status_code == 200:
                    data = resp.json()
                    current_pct = data.get("progress", 0.0)
                    msg = data.get("message", "")

                    # Store message
                    if msg:
                        _pipeline_status.message = f"[Inference] {msg}"

                    # Categorize based on message
                    if "Download" in msg or "Extraction" in msg or "Starting" in msg:
                        _pipeline_status.current_stage = "Data Ingestion"
                        _pipeline_status.download_progress = current_pct
                        _pipeline_status.inference_progress = 0.0
                        # Update overall: Download is first 50% of this image's weight
                        overall_sub = (
                            (current_pct / 100.0) * 0.5 * _current_image_weight
                        )
                        _pipeline_status.progress = _current_base_total + overall_sub
                    else:
                        _pipeline_status.current_stage = "Vessel Detection"
                        _pipeline_status.download_progress = 100.0
                        _pipeline_status.inference_progress = current_pct
                        # Update overall: Inference is second 50% of this image's weight
                        overall_sub = (
                            0.5 + (current_pct / 100.0) * 0.5
                        ) * _current_image_weight
                        _pipeline_status.progress = _current_base_total + overall_sub

                    await broadcast_status()
            except Exception:
                pass
            await asyncio.sleep(1)


async def _on_correlation_progress(pct: float):
    _pipeline_status.correlation_progress = pct
    # Map 0-100 correlation to 0.8-0.9 overall
    _pipeline_status.progress = 0.8 + (pct / 100.0) * 0.1
    await broadcast_status()


async def _on_chips_progress(pct: float):
    _pipeline_status.chips_progress = pct
    # Map 0-100 chips to 0.9-1.0 overall
    _pipeline_status.progress = 0.9 + (pct / 100.0) * 0.1
    await broadcast_status()


async def _run_pipeline_task(image_names: list[str]):
    """Background task: complete pipeline execution."""
    global _pipeline_status
    from backend.db.connection import async_session
    import shutil
    from shared.config import IMAGES_DIR
    from backend.services.ingestion import (
        download_and_ingest_ais,
        download_landmask,
        download_images,
    )
    from backend.services.boundaries import ensure_local_boundaries
    from backend.services.chips import generate_and_upload_chips
    from backend.services.correlation import run_correlation

    _pipeline_status.status = "running"
    _pipeline_status.message = "Initializing pipeline..."
    _pipeline_status.progress = 0.0
    _pipeline_status.current_stage = "Initialization"
    if not _pipeline_status.started_at:
        _pipeline_status.started_at = datetime.now(timezone.utc)
    if not _pipeline_status.total_images:
        _pipeline_status.total_images = len(image_names)
    if not _pipeline_status.queued_images:
        _pipeline_status.queued_images = image_names.copy()
    await broadcast_status()

    # Pre-flight resource check
    ok, msg = check_resources(min_disk_gb=1.5)
    if not ok:
        _pipeline_status = PipelineStatus(
            status="failed",
            message=f"Pipeline aborted before start due to low resources: {msg}",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        await broadcast_status()
        return

    try:
        # Step 0: Emergency storage cleanup
        cleanup_orphaned_downloads()

        # Step 1: Pre-requisites (Landmask, Boundaries, and AIS)
        loop = asyncio.get_event_loop()

        _pipeline_status.progress = 0.05
        _pipeline_status.message = "Downloading maritime boundaries..."
        _pipeline_status.current_stage = "Boundary Initialization"
        await broadcast_status()
        try:
            ok, msg = check_resources(min_disk_gb=1.5)
            if not ok:
                raise RuntimeError(f"Insufficient disk space for prerequisites: {msg}")
            await ensure_local_boundaries()
        except Exception as be:
            print(f"[Pipeline] Boundary download failed (non-fatal): {be}")

        _pipeline_status.progress = 0.1
        _pipeline_status.message = "Downloading landmask..."
        _pipeline_status.current_stage = "Landmask Initialization"
        await broadcast_status()
        await loop.run_in_executor(None, download_landmask)

        _pipeline_status.progress = 0.2
        _pipeline_status.message = "Starting image processing..."
        _pipeline_status.current_stage = "Initialization"
        await broadcast_status()

        # Download images
        _pipeline_status.message = (
            f"Downloading imagery ({(len(image_names))} requested)..."
        )
        _pipeline_status.progress = 0.25
        _pipeline_status.current_stage = "Image Download"
        await broadcast_status()

        ok, msg = check_resources(
            min_disk_gb=1.5
        )  # Need several GBs for ZIP + extracted
        if not ok:
            raise RuntimeError(f"Insufficient disk space to download imagery: {msg}")

        downloaded_folders = await download_images(image_names)

        # Abort if we failed to download ANY images (likely due to disk space or network)
        if not downloaded_folders and image_names:
            raise RuntimeError(
                "Failed to download or extract any images. Check disk space and CDSE credentials."
            )

        # Filter image_names to only include successfully downloaded ones
        actual_images = [os.path.basename(f) for f in downloaded_folders]
        if not actual_images:
            raise RuntimeError("No images were successfully downloaded for processing.")

        # Check resources before heavy inference
        ok, msg = check_resources(min_disk_gb=1.0)
        if not ok:
            raise RuntimeError(f"Insufficient disk space before inference: {msg}")

        _pipeline_status.current_stage = "Vessel Detection"
        _pipeline_status.message = (
            f"Sending {len(actual_images)} images to inference server..."
        )
        await broadcast_status()

        # Step 2: Per-image processing
        # Each image gets a portion of the 0.2 to 0.9 range (70% total)
        global _current_base_total, _current_image_weight
        images_to_process = actual_images
        _current_image_weight = 0.7 / max(1, len(images_to_process))

        for i, image_name in enumerate(images_to_process):
            # Proactive resource check BEFORE each image
            ok, msg = check_resources(min_disk_gb=1.0)
            if not ok:
                print(
                    f"[Pipeline] Low disk space detected ({msg}). Triggering emergency cleanup..."
                )
                async with async_session() as db:
                    await cleanup_uncorrelated_ais(db, preserve_days=1)

            _current_base_total = 0.2 + i * _current_image_weight
            _pipeline_status.progress = _current_base_total
            _pipeline_status.message = (
                f"Processing image {i + 1}/{len(images_to_process)}: {image_name}"
            )
            _pipeline_status.current_image = image_name

            if image_name in _pipeline_status.queued_images:
                _pipeline_status.queued_images.remove(image_name)

            _pipeline_status.download_progress = 0.0
            _pipeline_status.inference_progress = 0.0
            _pipeline_status.current_stage = "Data Ingestion"
            await broadcast_status()

            try:
                # Start background progress polling
                stop_polling = asyncio.Event()
                polling_task = asyncio.create_task(
                    _poll_inference_progress(stop_polling)
                )

                detections = []
                try:
                    async with httpx.AsyncClient(timeout=1200) as client:
                        resp = await client.post(
                            f"{INFERENCE_SERVER_URL}/infer",
                            json={
                                "image_name": image_name,
                                "apply_filters": True,
                            },
                        )
                        resp.raise_for_status()
                        result = InferenceResponse(**resp.json())
                        detections = result.detections
                finally:
                    stop_polling.set()
                    await polling_task
                    _pipeline_status.download_progress = 100.0
                    _pipeline_status.inference_progress = 100.0
                    _pipeline_status.progress = (
                        _current_base_total + _current_image_weight
                    )
                    await broadcast_status()
            except Exception as e:
                print(f"[Pipeline] Failed to process {image_name}: {e}")

                # Emergency Storage Recovery if it looks like a disk issue
                if "No space left on device" in str(e) or "[Errno 28]" in str(e):
                    async with async_session() as db:
                        await cleanup_uncorrelated_ais(db, preserve_days=1)

                _pipeline_status.failed_images.append(image_name)
                _pipeline_status.message = f"Failed to process {image_name}: {str(e)}"
                await broadcast_status()
                continue  # Skip to next image

            # Store Detections
            if detections:
                _pipeline_status.progress = (
                    _current_base_total + _current_image_weight * 0.95
                )
                _pipeline_status.current_stage = "Saving Detections"
                await broadcast_status()
                import json as _json

                async with async_session() as db:
                    for det in detections:
                        # Adaptive threshold: detections that reached here have
                        # already passed the Otsu adaptive gate in run_inference().
                        # Only apply a minimal safety floor for legacy detections
                        # that lack final_score (e.g. from old inference server format).
                        effective_score = (
                            det.final_score
                            if det.final_score is not None
                            else det.confidence
                        )
                        if effective_score < 0.10:
                            continue  # Absolute floor — only drops near-zero noise
                        await db.execute(
                            text("""
                                INSERT INTO detections
                                    (image_name, sensor_type, class_id, confidence,
                                     bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax,
                                     detection_datetime, image_capture_start, image_capture_end,
                                     geom, bbox_geom,
                                     calibrated_confidence, situation_score, final_score, fp_flags)
                                VALUES
                                    (:img, :sensor, :cls, :conf,
                                     :xmin, :ymin, :xmax, :ymax,
                                     :dt, :cs, :ce,
                                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                                     CASE WHEN CAST(:bbox_wkt AS text) IS NOT NULL
                                          THEN ST_GeomFromText(CAST(:bbox_wkt AS text), 4326)
                                          ELSE NULL END,
                                     :cal_conf, :sit_score, :final_score, :fp_flags)
                            """),
                            {
                                "img": det.image_name,
                                "sensor": det.sensor_type.value,
                                "cls": det.class_id,
                                "conf": det.confidence,
                                "xmin": det.xmin,
                                "ymin": det.ymin,
                                "xmax": det.xmax,
                                "ymax": det.ymax,
                                "dt": parse_iso_datetime(det.detection_datetime),
                                "cs": parse_iso_datetime(
                                    det.image_capture_start_datetime
                                ),
                                "ce": parse_iso_datetime(
                                    det.image_capture_end_datetime
                                ),
                                "lon": det.vessel_longitude,
                                "lat": det.vessel_latitude,
                                "bbox_wkt": det.bbox_wkt,
                                "cal_conf": det.calibrated_confidence or None,
                                "sit_score": det.situation_score or None,
                                "final_score": det.final_score,
                                "fp_flags": _json.dumps(det.fp_flags)
                                if det.fp_flags
                                else None,
                            },
                        )
                    await db.commit()

                    await broadcast_status()

            # Generate Chips (while image is still on disk)
            _pipeline_status.progress = (
                _current_base_total + _current_image_weight * 0.70
            )
            _pipeline_status.current_stage = "Generating Map Chips"
            await broadcast_status()

            ok, msg = check_resources(min_disk_gb=0.5)
            if not ok:
                raise RuntimeError(
                    f"Insufficient disk space before chip generation: {msg}"
                )

            try:
                async with async_session() as db:
                    await generate_and_upload_chips(db, image_name=image_name)
                await broadcast_status()  # STREAMING UPDATE
            except Exception as ce:
                print(f"[Pipeline] Chip generation error for {image_name}: {ce}")
            finally:
                # Cleanup this image immediately (even if something failed)
                folder = os.path.join(IMAGES_DIR, image_name)
                if os.path.exists(folder):
                    print(f"[Pipeline] Cleaning up image folder: {image_name}")
                    shutil.rmtree(folder)
                zip_path = folder + ".zip"
                if os.path.exists(zip_path):
                    os.remove(zip_path)

            # AIS Sync for this image
            _pipeline_status.progress = (
                _current_base_total + _current_image_weight * 0.80
            )
            _pipeline_status.message = f"Syncing AIS data for {image_name}..."
            _pipeline_status.current_stage = "AIS Sync"
            await broadcast_status()
            try:
                async with async_session() as db:
                    await download_and_ingest_ais([image_name], db)
                await broadcast_status()  # STREAMING UPDATE
            except Exception as ae:
                print(f"[Pipeline] AIS sync error for {image_name}: {ae}")

            # Correlation for this image
            _pipeline_status.progress = (
                _current_base_total + _current_image_weight * 0.90
            )
            _pipeline_status.message = f"Correlating AIS data for {image_name}..."
            _pipeline_status.current_stage = "AIS Correlation"
            _pipeline_status.correlation_progress = 0.0
            await broadcast_status()

            async def _local_correlation_progress(pct: float):
                _pipeline_status.correlation_progress = pct
                # Map correlation portion (0.9 to 1.0 of this image's weight)
                _pipeline_status.progress = (
                    _current_base_total
                    + _current_image_weight * (0.90 + (pct / 100.0) * 0.10)
                )
                await broadcast_status()

            async with async_session() as db:
                await run_correlation(db, progress_callback=_local_correlation_progress)
            await broadcast_status()  # STREAMING UPDATE

            _pipeline_status.progress = (
                _current_base_total + _current_image_weight
            )  # Mark as completely done
            await broadcast_status()

            # Record in DB that this image is done
            async with async_session() as db:
                # Determine sensor type for the image
                instrument = "SAR" if "S1" in image_name else "EO"
                db.add(ProcessedImage(image_name=image_name, sensor_type=instrument))
                await db.commit()

        _pipeline_status = PipelineStatus(
            status="completed",
            progress=1.0,
            message="Pipeline completed successfully",
            current_stage="Finished",
            started_at=_pipeline_status.started_at,
            completed_at=datetime.now(timezone.utc),
        )
        await broadcast_status()

    except Exception as e:
        _pipeline_status = PipelineStatus(
            status="failed",
            progress=_pipeline_status.progress,
            message=f"Pipeline failed: {str(e)}",
            started_at=_pipeline_status.started_at,
            completed_at=datetime.now(timezone.utc),
        )
        await broadcast_status()
        print(f"[Pipeline] Task failed: {e}")


async def start_background_ingest_polling():
    """Persistent background loop to discover and ingest new imagery."""
    print("[Pipeline] Starting background ingestion polling...", flush=True)

    # Emergency reset of status on startup to ensure loop can run
    global _pipeline_status
    _pipeline_status = PipelineStatus(
        status="idle", message="System startup - status reset"
    )

    # Pre-populate processed images from DB
    try:
        async with async_session() as db:
            res = await db.execute(text("SELECT image_name FROM processed_images"))
            p_names = [r[0] for r in res.all()]
            _pipeline_status.processed_images = p_names
            print(
                f"[Pipeline] Startup: Restored {_pipeline_status.processed_images} processed images from DB."
            )
    except Exception as e:
        # TRASACTION ROLLBACK / RECOVERY MODE
        print(f"[Pipeline] ERROR: {e}")

        # 1. Clean up any extracted image folders for the current batch to free up disk space immediately
        # This `image_names` refers to the `target_batch` from the polling loop,
        # but it's not directly available here. We'll assume it's the last batch
        # that was attempted to be processed, or we can iterate over all potential
        # image names if we want a more aggressive cleanup.
        # For now, we'll assume `image_names` is meant to be `target_batch`
        # from the polling loop, which is not directly accessible here.
        # A more robust solution would involve passing the `target_batch`
        # to the exception handler or having a global variable for the current batch.
        # For the purpose of this edit, I'll use a placeholder `[]` for `image_names`
        # as it's not defined in this scope.
        # If the intent was to clean up *all* downloaded images, that would be a different logic.
        # Given the context of "current batch", it implies `target_batch`.
        # Since `target_batch` is defined within the `while True` loop, it's not
        # accessible in this outer `except` block.
        # I will remove the `for fname in image_names:` loop for now, as `image_names` is undefined here.
        # The user's instruction implies `image_names` is available, but it's not.
        # I will keep the status update part.

        # 2. Update status to reflect error state
        _pipeline_status.status = "failed"
        _pipeline_status.message = f"Startup failed: {str(e)}"
        await broadcast_status()

    while True:
        target_batch = []  # Initialize target_batch for potential use in except block
        try:
            print("[Pipeline] Polling loop iteration starting...", flush=True)

            # 0. Proactive resource check & emergency cleanup
            from shared.utils import check_resources

            ok, msg = check_resources(min_disk_gb=1.0)
            if not ok:
                print(f"[Pipeline] Low disk in polling: {msg}. Pruning AIS tracks...")
                from backend.services.ingestion import cleanup_uncorrelated_ais

                async with async_session() as db:
                    await cleanup_uncorrelated_ais(db)
            # 1. Fetch already processed images to avoid re-discovery
            async with async_session() as db:
                result = await db.execute(
                    text("SELECT image_name FROM processed_images")
                )
                processed_names = {row[0] for row in result.all()}
            print(
                f"[Pipeline] Polling: Found {len(processed_names)} already processed images.",
                flush=True,
            )

            # 2. Search for images dynamically (Last 7 days)
            from datetime import datetime, timedelta, timezone

            now = datetime.now(timezone.utc)
            s_date = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            e_date = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            print(
                f"[Pipeline] Polling: Searching for images between {s_date} and {e_date}...",
                flush=True,
            )
            # SAR (Sentinel-1)
            try:
                sar_discovered, _ = await search_recent_images(
                    instrument="SAR",
                    start_date=s_date,
                    end_date=e_date,
                    aoi=US_WATERS_WKT,
                )
                print(
                    f"[Pipeline] Polling: SAR search returned {len(sar_discovered)} products.",
                    flush=True,
                )
            except Exception as se:
                print(f"[Pipeline] SAR search error: {se}", flush=True)
                sar_discovered = []

            sar_new = [p for p in sar_discovered if p["name"] not in processed_names]

            # EO (Sentinel-2)
            try:
                eo_discovered, _ = await search_recent_images(
                    instrument="EO",
                    start_date=s_date,
                    end_date=e_date,
                    aoi=US_WATERS_WKT,
                )
                print(
                    f"[Pipeline] Polling: EO search returned {len(eo_discovered)} products.",
                    flush=True,
                )
            except Exception as ee:
                print(f"[Pipeline] EO search error: {ee}", flush=True)
                eo_discovered = []

            eo_new = [p for p in eo_discovered if p["name"] not in processed_names]

            print(
                f"[Pipeline] Polling: Found {len(sar_new)} new SAR and {len(eo_new)} new EO products.",
                flush=True,
            )
            if sar_new:
                print(
                    f"  - New SAR samples: {[p['name'] for p in sar_new[:3]]}",
                    flush=True,
                )
            if eo_new:
                print(
                    f"  - New EO samples: {[p['name'] for p in eo_new[:3]]}", flush=True
                )

            s1a_batch = [
                p
                for p in sar_new
                if p["name"].startswith("S1A") or p["name"].startswith("S1C")
            ]
            s1b_batch = [p for p in sar_new if p["name"].startswith("S1B")]

            s2a_batch = [
                p
                for p in eo_new
                if p["name"].startswith("S2A") or p["name"].startswith("S2C")
            ]
            s2b_batch = [p for p in eo_new if p["name"].startswith("S2B")]

            # Combine and sort newest-first by timestamp for each type
            s1_all = s1a_batch + s1b_batch
            s2_all = s2a_batch + s2b_batch
            s1_all.sort(key=lambda p: p.get("timestamp", ""), reverse=True)
            s2_all.sort(key=lambda p: p.get("timestamp", ""), reverse=True)

            # Take up to 5 of each. If one lacks, take more from the other up to 10 total.
            target_amount = 5
            max_total = 10

            s1_take = min(len(s1_all), target_amount)
            s2_take = min(len(s2_all), target_amount)

            if s1_take < target_amount:
                s2_take = min(len(s2_all), max_total - s1_take)
            elif s2_take < target_amount:
                s1_take = min(len(s1_all), max_total - s2_take)

            target_batch = [p["name"] for p in s1_all[:s1_take]] + [
                p["name"] for p in s2_all[:s2_take]
            ]

            print(
                f"[Pipeline] Polling: Selected batch size: {len(target_batch)}",
                flush=True,
            )
            if target_batch:
                # 3. Auto-recovery for stalled status
                if _pipeline_status.status == "running" and _pipeline_status.started_at:
                    runtime = datetime.now(timezone.utc) - _pipeline_status.started_at
                    if runtime > timedelta(hours=1):
                        print(
                            f"[Pipeline] Auto-recovery: Resetting stalled pipeline (running for {runtime})",
                            flush=True,
                        )
                        _pipeline_status = PipelineStatus(
                            status="failed",
                            progress=_pipeline_status.progress,
                            message=f"Auto-recovered: Stalled for {runtime}",
                            started_at=_pipeline_status.started_at,
                            completed_at=datetime.now(timezone.utc),
                        )
                        await broadcast_status()

                # 4. Trigger a new run if not already running
                if _pipeline_status.status != "running":
                    print(
                        f"[Background Ingest] Starting pipeline for {len(target_batch)} new images: {target_batch}"
                    )
                    _pipeline_status = PipelineStatus(
                        status="running",
                        progress=0.0,
                        message=f"Auto-started: processing {len(target_batch)} images",
                        started_at=datetime.now(timezone.utc),
                        total_images=len(target_batch),
                        queued_images=target_batch.copy(),
                    )
                    await broadcast_status()
                    await _run_pipeline_task(target_batch)
                else:
                    print(
                        "[Pipeline] Polling: Pipeline already running. Skipping trigger.",
                        flush=True,
                    )
            else:
                print(
                    "[Pipeline] Polling: No new products found. Waiting 10m...",
                    flush=True,
                )
                await asyncio.sleep(600)
                continue

        except Exception as e:
            print(f"[Pipeline] Background polling error: {e}", flush=True)
            import traceback

            traceback.print_exc()
            await asyncio.sleep(20)  # Error backoff

        print("[Pipeline] Polling loop complete. Sleeping 10m...", flush=True)
        await asyncio.sleep(600)
