"""
Shared Pydantic schemas for communication between inference server and backend server.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class SensorType(str, Enum):
    SAR = "SAR"
    EO = "EO"


# ---------------------------------------------------------------------------
# Detection schemas
# ---------------------------------------------------------------------------
class Detection(BaseModel):
    """A single vessel detection produced by the inference server."""
    image_name: str
    sensor_type: SensorType
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    class_id: int = 0
    confidence: float
    bbox_wkt: str
    vessel_latitude: float
    vessel_longitude: float
    detection_datetime: Optional[str] = None
    image_capture_start_datetime: Optional[str] = None
    image_capture_end_datetime: Optional[str] = None


# ---------------------------------------------------------------------------
# Inference request / response
# ---------------------------------------------------------------------------
class InferenceRequest(BaseModel):
    """Request payload sent to the inference server."""
    sensor_type: Optional[SensorType] = None  # auto-detect if None
    image_name: Optional[str] = Field(
        None, description="Optional Copernicus product name to download and process"
    )
    image_folder_path: Optional[str] = Field(
        None, description="Absolute path to a single SAFE folder to process"
    )
    apply_filters: bool = Field(
        True, description="Whether to apply NMS/landmask/cloudmask filters"
    )


class InferenceResponse(BaseModel):
    """Response payload from the inference server."""
    detections: list[Detection]
    total_count: int
    sensor_type: SensorType
    processing_time_seconds: float


# ---------------------------------------------------------------------------
# AIS schemas
# ---------------------------------------------------------------------------
class AISTrackPoint(BaseModel):
    """A single AIS position report."""
    mmsi: int
    timestamp: datetime
    latitude: float
    longitude: float
    sog: Optional[float] = None
    cog: Optional[float] = None


class VesselCorrelation(BaseModel):
    """A detection correlated with an AIS vessel."""
    detection_id: int
    mmsi: int
    distance_meters: float
    vessel_latitude: float
    vessel_longitude: float
    detection_datetime: str


# ---------------------------------------------------------------------------
# Frontend-facing response schemas
# ---------------------------------------------------------------------------
class DetectionGeoJSON(BaseModel):
    """GeoJSON-compatible detection for Leaflet."""
    type: str = "Feature"
    geometry: dict
    properties: dict


class DetectionCluster(BaseModel):
    """Clustered detections for low zoom levels."""
    center_lat: float
    center_lon: float
    count: int
    bbox: list[float]  # [min_lon, min_lat, max_lon, max_lat]


class PipelineStatus(BaseModel):
    """Pipeline execution status."""
    status: str  # "idle", "running", "completed", "failed"
    progress: float = 0.0  # 0.0 - 1.0 (Total Progress)
    
    # Granular stage progress (0.0 - 100.0)
    download_progress: float = 0.0
    inference_progress: float = 0.0
    correlation_progress: float = 0.0
    chips_progress: float = 0.0
    
    message: str = ""
    current_stage: str = ""  # e.g., "Downloading", "Inferring"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_image: Optional[str] = None
    total_images: int = 0
    processed_images: list[str] = []
    failed_images: list[str] = []
    queued_images: list[str] = []
