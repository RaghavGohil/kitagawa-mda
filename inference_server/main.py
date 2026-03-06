"""
Inference Server — FastAPI application.

Exposes endpoints for running YOLO vessel detection on satellite imagery.
Uses the adapter pattern to support both SAR and EO sensors transparently.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from shared.config import DATA_DIR, IMAGES_DIR, MASK_DIR
from shared.schemas import (
    Detection,
    InferenceRequest,
    InferenceResponse,
    SensorType,
)

from inference_server.adapters.eo import EOAdapter
from inference_server.adapters.sar import SARAdapter
from inference_server.filters.pipeline import FilterPipeline

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
_adapters: dict[SensorType, SARAdapter | EOAdapter] = {}
_filter_pipeline: FilterPipeline | None = None


# ---------------------------------------------------------------------------
# Lifespan: load models once at startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _adapters, _filter_pipeline

    print("[Inference Server] Loading models...")

    sar_adapter = SARAdapter()
    sar_adapter.load_model()
    _adapters[SensorType.SAR] = sar_adapter

    eo_adapter = EOAdapter()
    eo_adapter.load_model()
    _adapters[SensorType.EO] = eo_adapter

    # Load filter pipeline
    landmask_path = os.path.join(MASK_DIR, "GSHHS_shp", "f", "GSHHS_f_L1.shp")
    print(f"[Inference Server] MASK_DIR = {MASK_DIR}")
    print(f"[Inference Server] Landmask path = {landmask_path}")
    print(f"[Inference Server] MASK_DIR exists: {os.path.exists(MASK_DIR)}")
    if os.path.exists(MASK_DIR):
        print(f"[Inference Server] MASK_DIR contents: {os.listdir(MASK_DIR)}")
        gshhs_dir = os.path.join(MASK_DIR, "GSHHS_shp")
        if os.path.exists(gshhs_dir):
            print(f"[Inference Server] GSHHS_shp contents: {os.listdir(gshhs_dir)}")
            f_dir = os.path.join(gshhs_dir, "f")
            if os.path.exists(f_dir):
                print(f"[Inference Server] f/ contents: {os.listdir(f_dir)}")
    print(f"[Inference Server] Landmask file exists: {os.path.exists(landmask_path)}")
    cloudmask_dir = os.path.join("inference_server", "filters")
    _filter_pipeline = FilterPipeline(
        landmask_shp_path=landmask_path,
        cloudmask_model_dir=cloudmask_dir,
    )

    print("[Inference Server] Models loaded. Ready to serve.")

    yield

    # Cleanup
    _adapters.clear()
    _filter_pipeline = None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Kitagawa Inference Server",
    description="YOLO vessel detection on SAR and EO satellite imagery",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    from shared.utils import check_resources, get_free_disk_gb, get_memory_usage_mb
    import psutil
    import os
    
    ok, msg = check_resources(min_disk_gb=0.5)
    data_dir = os.getenv("DATA_DIR", "/data")

    return {
        "status": "healthy" if ok else "resource_constrained",
        "models_loaded": list(_adapters.keys()),
        "filters_available": _filter_pipeline is not None,
        "resources": {
            "ok": ok,
            "message": msg,
            "free_disk_gb": round(get_free_disk_gb(data_dir if os.path.exists(data_dir) else "."), 2),
            "memory_percent": psutil.virtual_memory().percent,
            "process_memory_mb": round(get_memory_usage_mb(), 2)
        }
    }


@app.post("/infer", response_model=InferenceResponse)
def infer(request: InferenceRequest):
    """
    Run inference on a single SAFE folder.

    If image_name is provided, it will be downloaded automatically.
    If sensor_type is not provided, auto-detects from folder name prefix
    (S1 → SAR, S2 → EO).
    """
    t_start = time.time()
    folder_path = request.image_folder_path
    image_name = request.image_name
    temp_download = False

    # Scenario 1: Download by name
    if image_name and not folder_path:
        from inference_server.services.ingestion import download_single_image
        print(f"[Inference] Downloading product: {image_name}")
        folder_path = download_single_image(image_name)
        if not folder_path:
            raise HTTPException(
                status_code=404,
                detail=f"Product not found or download failed for: {image_name}",
            )
        temp_download = True

    if not folder_path or not os.path.isdir(folder_path):
        raise HTTPException(
            status_code=404,
            detail=f"Folder not found: {folder_path}",
        )

    # Auto-detect sensor type
    sensor_type = request.sensor_type
    if sensor_type is None:
        folder_name = os.path.basename(folder_path)
        if folder_name.startswith("S1"):
            sensor_type = SensorType.SAR
        elif folder_name.startswith("S2"):
            sensor_type = SensorType.EO
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot auto-detect sensor type for: {folder_name}. "
                "Provide sensor_type explicitly.",
            )

    adapter = _adapters.get(sensor_type)
    if adapter is None:
        raise HTTPException(
            status_code=500,
            detail=f"Adapter not loaded for sensor type: {sensor_type}",
        )

    detections = adapter.process_folder(folder_path)

    # Apply filters
    if request.apply_filters and _filter_pipeline:
        detections = _filter_pipeline.apply(detections)

    # Cleanup will be handled by the backend after chip generation
    # if temp_download:
    #     import shutil
    #     print(f"[Inference] Cleaning up temporary folder: {folder_path}")
    #     try:
    #         shutil.rmtree(folder_path)
    #     except Exception as e:
    #         print(f"[Inference] Cleanup failed: {e}")

    elapsed = time.time() - t_start

    return InferenceResponse(
        detections=detections,
        total_count=len(detections),
        sensor_type=sensor_type,
        processing_time_seconds=round(elapsed, 2),
    )

@app.get("/progress")
async def get_progress():
    """Get the current ingestion/download progress."""
    from inference_server.services.ingestion import progress_tracker
    return progress_tracker.get_status()


@app.post("/infer/batch")
def infer_batch(
    root_dir: str = IMAGES_DIR,
    apply_filters: bool = True,
):
    """
    Run inference on ALL SAFE folders found in root_dir.
    Processes SAR and EO folders automatically.
    """
    t_start = time.time()
    all_detections: list[Detection] = []

    for sensor_type, adapter in _adapters.items():
        folders = adapter.find_image_folders(root_dir)
        for folder in folders:
            try:
                dets = adapter.process_folder(folder)
                all_detections.extend(dets)
            except Exception as e:
                print(f"[WARN] Error processing {folder}: {e}")

    if apply_filters and _filter_pipeline:
        all_detections = _filter_pipeline.apply(all_detections)

    elapsed = time.time() - t_start

    return InferenceResponse(
        detections=all_detections,
        total_count=len(all_detections),
        sensor_type=SensorType.SAR,  # mixed
        processing_time_seconds=round(elapsed, 2),
    )
