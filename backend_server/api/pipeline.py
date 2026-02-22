"""
Pipeline API — triggering data ingestion, inference, and correlation.

Provides endpoints for orchestrating the full data processing pipeline
from the HTTP API instead of requiring CLI/Prefect.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from shared.config import IMAGES_DIR, INFERENCE_SERVER_URL
from shared.schemas import InferenceResponse, PipelineStatus
from backend_server.db.connection import get_db, async_session
from backend_server.db.models import ProcessedImage
from backend_server.services.ingestion import search_recent_images

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
                if now - os.path.getmtime(path) > 7200: # 2 hours
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
async def search_copernicus(instrument: str = "SAR", days: int = 7):
    """Search for available images in Copernicus."""
    results = search_recent_images(instrument, days)
    return {"results": results}


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
    print(f"[Pipeline] Manual reset triggered. Previous state: {_pipeline_status.status}")
    _pipeline_status = PipelineStatus(
        status="idle",
        message="Manually reset via API",
        completed_at=datetime.now(timezone.utc)
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
                        overall_sub = (current_pct / 100.0) * 0.5 * _current_image_weight
                        _pipeline_status.progress = _current_base_total + overall_sub
                    else:
                        _pipeline_status.current_stage = "Vessel Detection"
                        _pipeline_status.download_progress = 100.0
                        _pipeline_status.inference_progress = current_pct
                        # Update overall: Inference is second 50% of this image's weight
                        overall_sub = (0.5 + (current_pct / 100.0) * 0.5) * _current_image_weight
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

    from backend_server.db.connection import async_session
    from backend_server.services.ingestion import (
        download_and_ingest_ais,
        download_images,
        download_landmask,
    )
    from backend_server.services.correlation import run_correlation
    from backend_server.services.chips import generate_and_upload_chips

    try:
        # Step 0: Emergency storage cleanup
        cleanup_orphaned_downloads()

        # Step 1: Pre-requisites (Landmask and AIS)
        loop = asyncio.get_event_loop()

        _pipeline_status.progress = 0.1
        _pipeline_status.message = "Downloading landmask..."
        _pipeline_status.current_stage = "Landmask Initialization"
        await broadcast_status()
        await loop.run_in_executor(None, download_landmask)

        _pipeline_status.progress = 0.2
        _pipeline_status.message = "Starting AIS sync and image processing task..."
        _pipeline_status.current_stage = "Initialization"
        await broadcast_status()
        
        # Start AIS ingestion as a background task
        async def run_ais_task():
            async with async_session() as db:
                await download_and_ingest_ais(image_names, db)
        
        ais_task = asyncio.create_task(run_ais_task())

        # Step 2: Per-image processing
        # Each image gets a portion of the 0.2 to 0.8 range (60% total)
        global _current_base_total, _current_image_weight
        images_to_process = image_names
        _current_image_weight = 0.6 / max(1, len(images_to_process))
        
        for i, image_name in enumerate(images_to_process):
            _current_base_total = 0.2 + i * _current_image_weight
            _pipeline_status.progress = _current_base_total
            _pipeline_status.message = f"Processing image {i+1}/{len(images_to_process)}: {image_name}"
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
                polling_task = asyncio.create_task(_poll_inference_progress(stop_polling))
                
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
                    _pipeline_status.progress = _current_base_total + _current_image_weight
                    await broadcast_status()
            except Exception as e:
                print(f"[Pipeline] Failed to process {image_name}: {e}")
                _pipeline_status.failed_images.append(image_name)
                _pipeline_status.message = f"Failed to process {image_name}: {str(e)}"
                await broadcast_status()
                continue # Skip to next image

            # Store Detections
            if detections:
                _pipeline_status.progress = _current_base_total + _current_image_weight * 0.95
                _pipeline_status.current_stage = "Saving Detections"
                await broadcast_status()
                async with async_session() as db:
                    for det in detections:
                        if det.confidence < 0.80:
                            continue
                        await db.execute(
                            text("""
                                INSERT INTO detections
                                    (image_name, sensor_type, class_id, confidence,
                                     bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax,
                                     detection_datetime, image_capture_start, image_capture_end,
                                     geom, bbox_geom)
                                VALUES
                                    (:img, :sensor, :cls, :conf,
                                     :xmin, :ymin, :xmax, :ymax,
                                     :dt, :cs, :ce,
                                     ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                                     CASE WHEN CAST(:bbox_wkt AS text) IS NOT NULL
                                          THEN ST_GeomFromText(CAST(:bbox_wkt AS text), 4326)
                                          ELSE NULL END)
                            """),
                            {
                                "img": det.image_name,
                                "sensor": det.sensor_type.value,
                                "cls": det.class_id,
                                "conf": det.confidence,
                                "xmin": det.xmin, "ymin": det.ymin,
                                "xmax": det.xmax, "ymax": det.ymax,
                                "dt": parse_iso_datetime(det.detection_datetime),
                                "cs": parse_iso_datetime(det.image_capture_start_datetime),
                                "ce": parse_iso_datetime(det.image_capture_end_datetime),
                                "lon": det.vessel_longitude,
                                "lat": det.vessel_latitude,
                                "bbox_wkt": det.bbox_wkt,
                            },
                        )
                    await db.commit()

            # Generate Chips (while image is still on disk)
            _pipeline_status.progress = _current_base_total + _current_image_weight * 0.98
            _pipeline_status.current_stage = "Generating Map Chips"
            await broadcast_status()
            async with async_session() as db:
                await generate_and_upload_chips(db)

            # Cleanup this image immediately (if folder exists from old runs)
            import shutil
            folder = os.path.join(IMAGES_DIR, image_name)
            if os.path.exists(folder):
                shutil.rmtree(folder)
            zip_path = folder + ".zip"
            if os.path.exists(zip_path):
                os.remove(zip_path)
            
            _pipeline_status.processed_images.append(image_name)
            _pipeline_status.progress = _current_base_total + _current_image_weight # Mark as completely done
            await broadcast_status()
            
            # Record in DB that this image is done
            async with async_session() as db:
                await db.execute(
                    text("INSERT INTO processed_images (image_name, sensor_type) VALUES (:name, :sensor) ON CONFLICT (image_name) DO NOTHING"),
                    {"name": image_name, "sensor": "SAR" if "S1" in image_name else "EO"}
                )
                await db.commit()

        # Step 5: Correlation
        # Wait for the AIS ingestion task to complete if it was started
        try:
            if 'ais_task' in locals():
                _pipeline_status.message = "Ensuring AIS sync is complete..."
                await broadcast_status()
                await ais_task
        except Exception as ae:
            print(f"[Pipeline] AIS task background error: {ae}")
            # We don't fail the whole pipeline if AIS ingestion partially failed,
            # as some AIS data might still be present.

        _pipeline_status.progress = 0.8
        _pipeline_status.message = "Running AIS correlation..."
        _pipeline_status.current_stage = "AIS Correlation"
        _pipeline_status.correlation_progress = 0.0
        await broadcast_status()
        async with async_session() as db:
            correlated = await run_correlation(db, progress_callback=_on_correlation_progress)
        _pipeline_status.correlation_progress = 100.0
        _pipeline_status.progress = 0.9
        await broadcast_status()

        # Step 6: Chips
        _pipeline_status.progress = 0.9
        _pipeline_status.message = "Generating thumbnails..."
        _pipeline_status.current_stage = "Thumbnail Generation"
        _pipeline_status.chips_progress = 0.0
        await broadcast_status()
        async with async_session() as db:
            await generate_and_upload_chips(db, progress_callback=_on_chips_progress)
        _pipeline_status.chips_progress = 100.0
        _pipeline_status.progress = 1.0
        await broadcast_status()

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
    _pipeline_status = PipelineStatus(status="idle", message="System startup - status reset")
    await broadcast_status()

    while True:
        try:
            print("[Pipeline] Polling loop iteration starting...", flush=True)
            # 1. Fetch already processed images to avoid re-discovery
            async with async_session() as db:
                result = await db.execute(text("SELECT image_name FROM processed_images"))
                processed_names = {row[0] for row in result.all()}
            print(f"[Pipeline] Polling: Found {len(processed_names)} already processed images.", flush=True)

            # 2. Search for images in 2025 filling the DB with compatible data
            s_date = "2025-01-01T00:00:00.000Z"
            e_date = "2025-06-01T00:00:00.000Z"
            
            print(f"[Pipeline] Polling: Searching for images between {s_date} and {e_date}...", flush=True)
            # SAR (Sentinel-1)
            try:
                sar_discovered = search_recent_images(instrument="SAR", start_date=s_date, end_date=e_date)
                print(f"[Pipeline] Polling: SAR search returned {len(sar_discovered)} products.", flush=True)
            except Exception as se:
                print(f"[Pipeline] SAR search error: {se}", flush=True)
                sar_discovered = []

            sar_new = [p for p in sar_discovered if p["name"] not in processed_names]
            
            # EO (Sentinel-2)
            try:
                eo_discovered = search_recent_images(instrument="EO", start_date=s_date, end_date=e_date)
                print(f"[Pipeline] Polling: EO search returned {len(eo_discovered)} products.", flush=True)
            except Exception as ee:
                print(f"[Pipeline] EO search error: {ee}", flush=True)
                eo_discovered = []

            eo_new = [p for p in eo_discovered if p["name"] not in processed_names]

            print(f"[Pipeline] Polling: Found {len(sar_new)} new SAR and {len(eo_new)} new EO products.", flush=True)
            if sar_new:
                print(f"  - New SAR samples: {[p['name'] for p in sar_new[:3]]}", flush=True)
            if eo_new:
                print(f"  - New EO samples: {[p['name'] for p in eo_new[:3]]}", flush=True)
            
            s1a_batch = [p for p in sar_new if p["name"].startswith("S1A")][:2] # Smaller batches for debugging
            s1b_batch = [p for p in sar_new if p["name"].startswith("S1B")][:2]
            
            s2a_batch = [p for p in eo_new if p["name"].startswith("S2A")][:2]
            s2b_batch = [p for p in eo_new if p["name"].startswith("S2B")][:2]
            
            # Combine into final target batch
            target_batch = [p["name"] for p in (s1a_batch + s1b_batch + s2a_batch + s2b_batch)]
            
            print(f"[Pipeline] Polling: Selected batch size: {len(target_batch)}", flush=True)
            if target_batch:
                # 3. Auto-recovery for stalled status
                if _pipeline_status.status == "running" and _pipeline_status.started_at:
                    runtime = datetime.now(timezone.utc) - _pipeline_status.started_at
                    if runtime > timedelta(hours=1):
                        print(f"[Pipeline] Auto-recovery: Resetting stalled pipeline (running for {runtime})", flush=True)
                        _pipeline_status = PipelineStatus(
                            status="failed",
                            progress=_pipeline_status.progress,
                            message=f"Auto-recovered: Stalled for {runtime}",
                            started_at=_pipeline_status.started_at,
                            completed_at=datetime.now(timezone.utc)
                        )
                        await broadcast_status()

                # 4. Trigger a new run if not already running
                if _pipeline_status.status != "running":
                    print(f"[Pipeline] Polling: Triggering background task for batch {target_batch[:2]}...", flush=True)
                    _pipeline_status = PipelineStatus(
                        status="running",
                        progress=0.0,
                        message=f"Auto-started: processing {len(target_batch)} images",
                        started_at=datetime.now(timezone.utc),
                        total_images=len(target_batch),
                        queued_images=target_batch.copy()
                    )
                    await broadcast_status()
                    asyncio.create_task(_run_pipeline_task(target_batch))
                else:
                    print("[Pipeline] Polling: Pipeline already running. Skipping trigger.", flush=True)
            else:
                print("[Pipeline] Polling: No new products found. Waiting 1h...", flush=True)
                await asyncio.sleep(3600)
                continue
            
        except Exception as e:
            print(f"[Pipeline] Background polling error: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        print("[Pipeline] Polling loop complete. Sleeping 1h...", flush=True)
        await asyncio.sleep(3600)
