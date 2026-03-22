"""
Pipeline API — triggering data ingestion, inference, and correlation.

Provides endpoints for orchestrating the full data processing pipeline
from the HTTP API instead of requiring CLI/Prefect.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime, timezone

import httpx
from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy import text, select

from shared.config import IMAGES_DIR, INFERENCE_SERVER_URL
from shared.schemas import InferenceResponse, PipelineStatus
from shared.utils import check_resources, parse_iso_datetime
from backend.db.connection import async_session
from backend.db.models import ProcessedImage
from backend.services.ingestion import (
    search_recent_images,
    cleanup_uncorrelated_ais,
    download_and_ingest_ais,
    download_landmask,
    download_images,
)
from backend.services.boundaries import ensure_local_boundaries
from backend.services.chips import generate_and_upload_chips
from backend.services.correlation import run_correlation
from backend.services.ais_stream import set_active_bboxes

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])

# Simple in-memory pipeline status tracker
_pipeline_status = PipelineStatus(status="idle")

# Asynchronous Task Queue for producers (polling/manual) and consumers (worker)
_image_queue: asyncio.Queue[str] = asyncio.Queue()


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
    """Broadcast the current pipeline status to all connected WebSockets."""
    await manager.broadcast(_pipeline_status.dict())


@router.websocket("/ws/status")
async def status_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json(_pipeline_status.dict())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.get("/status", response_model=PipelineStatus)
async def get_pipeline_status():
    if _pipeline_status.status == "idle" and not _image_queue.empty():
        _pipeline_status.message = f"Idle - {_image_queue.qsize()} images in queue"
    return _pipeline_status


@router.post("/run")
async def run_pipeline(image_names: list[str]):
    added = 0
    for name in image_names:
        if (
            name not in _pipeline_status.processed_images
            and name not in _pipeline_status.queued_images
        ):
            await _image_queue.put(name)
            _pipeline_status.queued_images.append(name)
            added += 1

    if added > 0:
        if _pipeline_status.status != "running":
            _pipeline_status.status = "running"
            _pipeline_status.started_at = datetime.now(timezone.utc)
        await broadcast_status()
    return {"status": "queued", "added": added}


@router.post("/reset")
async def reset_pipeline():
    global _pipeline_status
    _pipeline_status = PipelineStatus(status="idle", progress=0.0)
    while not _image_queue.empty():
        try:
            _image_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    await broadcast_status()
    return {"status": "reset"}


async def _poll_inference_progress(stop_event: asyncio.Event):
    async with httpx.AsyncClient(timeout=10) as client:
        while not stop_event.is_set():
            try:
                resp = await client.get(f"{INFERENCE_SERVER_URL}/progress")
                if resp.status_code == 200:
                    data = resp.json()
                    current_pct = data.get("progress", 0.0)
                    msg = data.get("message", "")
                    if "Download" in msg or "Extraction" in msg:
                        _pipeline_status.current_stage = "Image Download"
                        _pipeline_status.download_progress = current_pct
                    else:
                        _pipeline_status.current_stage = "Analysing Image"
                        _pipeline_status.inference_progress = current_pct
                    await broadcast_status()
            except Exception:
                pass
            await asyncio.sleep(1)


async def pipeline_worker():
    while True:
        image_name = await _image_queue.get()
        try:
            await _run_pipeline_task_single(image_name)
        except Exception as e:
            print(f"[Worker] Error {image_name}: {e}")
        finally:
            _image_queue.task_done()
            if _image_queue.empty():
                _pipeline_status.status = "completed"
                _pipeline_status.completed_at = datetime.now(timezone.utc)
                await broadcast_status()


async def _run_pipeline_task_single(image_name: str):
    _pipeline_status.status = "running"
    _pipeline_status.current_image = image_name
    if image_name in _pipeline_status.queued_images:
        _pipeline_status.queued_images.remove(image_name)
    await broadcast_status()

    try:
        await ensure_local_boundaries()
        async with async_session() as db:
            await download_and_ingest_ais([image_name], db)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, download_landmask)

        # 1. Download
        def on_dl_progress(pct: float, fname: str):
            _pipeline_status.download_progress = pct
            asyncio.run_coroutine_threadsafe(broadcast_status(), loop)

        downloaded = await asyncio.wait_for(
            download_images([image_name], progress_callback=on_dl_progress),
            timeout=1200,
        )
        if not downloaded:
            return

        # 2. Inference
        folder_path = downloaded[0]
        stop_polling = asyncio.Event()
        polling_task = asyncio.create_task(_poll_inference_progress(stop_polling))
        detections = []
        try:
            async with httpx.AsyncClient(timeout=1500) as client:
                resp = await client.post(
                    f"{INFERENCE_SERVER_URL}/infer",
                    json={"image_folder_path": folder_path, "apply_filters": True},
                )
                resp.raise_for_status()
                detections = InferenceResponse(**resp.json()).detections
            if detections:
                try:
                    lats = [
                        d.vessel_latitude
                        for d in detections
                        if d.vessel_latitude is not None
                    ]
                    lons = [
                        d.vessel_longitude
                        for d in detections
                        if d.vessel_longitude is not None
                    ]
                    if lats and lons:
                        bbox = [
                            [min(lats) - 0.2, min(lons) - 0.2],
                            [max(lats) + 0.2, max(lons) + 0.2],
                        ]
                        await set_active_bboxes([bbox])
                except Exception:
                    pass
        finally:
            stop_polling.set()
            await polling_task
            _pipeline_status.inference_progress = 100.0
            await broadcast_status()

        # Save & Chips & Correlation
        if detections:
            import json as _json

            async with async_session() as db:
                for det in detections:
                    if (det.final_score or det.confidence) < 0.10:
                        continue
                    await db.execute(
                        text("""
                        INSERT INTO detections (image_name, sensor_type, class_id, confidence, bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax, detection_datetime, image_capture_start, image_capture_end, geom, bbox_geom, calibrated_confidence, situation_score, final_score, fp_flags)
                        VALUES (:img, :sensor, :cls, :conf, :xmin, :ymin, :xmax, :ymax, :dt, :cs, :ce, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), CASE WHEN CAST(:bbox_wkt AS text) IS NOT NULL THEN ST_GeomFromText(CAST(:bbox_wkt AS text), 4326) ELSE NULL END, :cal_conf, :sit_score, :final_score, :fp_flags)
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
                            "cs": parse_iso_datetime(det.image_capture_start_datetime),
                            "ce": parse_iso_datetime(det.image_capture_end_datetime),
                            "lon": det.vessel_longitude,
                            "lat": det.vessel_latitude,
                            "bbox_wkt": det.bbox_wkt,
                            "cal_conf": det.calibrated_confidence,
                            "sit_score": det.situation_score,
                            "final_score": det.final_score,
                            "fp_flags": _json.dumps(det.fp_flags)
                            if det.fp_flags
                            else None,
                        },
                    )
                await db.commit()

        async with async_session() as db:
            await generate_and_upload_chips(db, image_name=image_name)

        folder = os.path.join(IMAGES_DIR, image_name)
        if os.path.exists(folder):
            shutil.rmtree(folder)
        if os.path.exists(folder + ".zip"):
            os.remove(folder + ".zip")

        async with async_session() as db:
            await run_correlation(db, image_name=image_name)

            # Use ON CONFLICT DO NOTHING behavior or verify existence to avoid IntegrityError
            stmt = select(ProcessedImage).where(ProcessedImage.image_name == image_name)
            existing = (await db.execute(stmt)).scalar_one_or_none()

            if not existing:
                db.add(
                    ProcessedImage(
                        image_name=image_name,
                        sensor_type="SAR" if "S1" in image_name else "EO",
                    )
                )
                await db.commit()
            else:
                await db.rollback()  # Not needed but good practice after select

        if image_name not in _pipeline_status.processed_images:
            _pipeline_status.processed_images.append(image_name)
        await set_active_bboxes(None)
        await broadcast_status()

    except Exception as e:
        print(f"[Pipeline] Failed {image_name}: {e}")
        _pipeline_status.failed_images.append(image_name)
        await broadcast_status()


async def start_background_ingest_polling():
    while True:
        try:
            ok, _ = check_resources(min_disk_gb=1.0)
            if not ok:
                async with async_session() as db:
                    await cleanup_uncorrelated_ais(db)

            sar, _ = await search_recent_images("SAR", days=0.5, limit=5)
            eo, _ = await search_recent_images("EO", days=0.5, limit=5)
            for p in sar + eo:
                name = p["name"]
                if (
                    name not in _pipeline_status.processed_images
                    and name not in _pipeline_status.queued_images
                ):
                    await _image_queue.put(name)
                    _pipeline_status.queued_images.append(name)
        except Exception:
            await asyncio.sleep(60)
        await asyncio.sleep(600)
