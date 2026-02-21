"""
Abstract base class for sensor-specific inference adapters.

The adapter pattern provides clean separation between SAR and EO processing
while sharing the common YOLO inference pipeline. Each sensor has different:
  - Image reading (TIFF vs JP2, single band vs RGB)
  - Patch preprocessing (min-max norm vs 8-bit conversion)
  - Georeferencing (GCPs vs CRS transform)
  - Datetime extraction (calibration XML vs sensing time XML)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
import torch
from ultralytics import YOLO

from shared.schemas import Detection, SensorType


# ---------------------------------------------------------------------------
# Data classes for structured intermediate data
# ---------------------------------------------------------------------------
@dataclass
class ImageMetadata:
    """Metadata extracted from a SAFE folder."""
    safe_folder: str
    image_name: str
    sensor_type: SensorType
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    width: int = 0
    height: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class PatchBatch:
    """A batch of image patches ready for inference."""
    tiles: np.ndarray          # shape [B, 3, H, W], float32
    positions: list[tuple[int, int]]  # (row, col) per tile
    metadata: ImageMetadata    # source image metadata


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------
class SensorAdapter(ABC):
    """
    Base class for sensor-specific inference adapters.

    Subclasses must implement:
      - sensor_type: the SensorType enum value
      - model_path: path to the YOLO .pt weights
      - patch_size / stride / conf_threshold / batch_size / imgsz
      - preprocess_image(): read image, generate patch batches
      - postprocess_detections(): georeference raw YOLO boxes
      - compute_detection_datetime(): per-detection timestamp
    """

    # --- Subclass must set these ---
    sensor_type: SensorType
    model_path: str
    patch_size: int
    stride: int
    conf_threshold: float
    batch_size: int
    imgsz: int  # YOLO input resolution

    def __init__(self):
        self._model: Optional[YOLO] = None
        self._device: str = "cuda:0" if torch.cuda.is_available() else "cpu"

    # ----- Model management -----
    def load_model(self) -> None:
        """Load the YOLO model and move to device."""
        if self._model is not None:
            return
        self._model = YOLO(self.model_path)
        try:
            self._model.to(self._device)
        except Exception:
            pass  # some ultralytics versions manage device internally

    @property
    def model(self) -> YOLO:
        if self._model is None:
            self.load_model()
        return self._model

    @property
    def device(self) -> str:
        return self._device

    # ----- Abstract methods -----
    @abstractmethod
    def find_image_folders(self, root_dir: str) -> list[str]:
        """Find all SAFE folders for this sensor type in root_dir."""
        ...

    @abstractmethod
    def parse_metadata(self, safe_folder: str) -> ImageMetadata:
        """Extract metadata from a SAFE folder."""
        ...

    @abstractmethod
    def preprocess_image(self, safe_folder: str, metadata: ImageMetadata) -> list[PatchBatch]:
        """
        Read the image from a SAFE folder and generate patch batches.
        Returns a list of PatchBatch objects ready for run_inference().
        """
        ...

    @abstractmethod
    def georeference_box(
        self, x1: float, y1: float, x2: float, y2: float,
        metadata: ImageMetadata
    ) -> Optional[tuple[str, float, float]]:
        """
        Convert pixel bbox to geographic coordinates.
        Returns (bbox_wkt, centroid_lat, centroid_lon) or None on failure.
        """
        ...

    @abstractmethod
    def compute_detection_datetime(
        self, ymin: float, ymax: float, metadata: ImageMetadata
    ) -> Optional[str]:
        """
        Compute the precise detection datetime from the row position.
        Returns ISO-format string or None.
        """
        ...

    # ----- Common inference pipeline -----
    def run_inference(self, batch: PatchBatch) -> list[Detection]:
        """
        Run YOLO inference on a batch and return georeferenced detections.
        This method is shared across all sensor adapters.
        """
        tiles = torch.tensor(batch.tiles, dtype=torch.float32, device=self._device)

        results = self.model.predict(
            tiles,
            imgsz=self.imgsz,
            conf=self.conf_threshold,
            verbose=False,
            device=self._device,
        )

        detections: list[Detection] = []

        for idx, res in enumerate(results):
            row, col = batch.positions[idx]
            for box in res.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
                conf = float(box.conf[0].cpu().numpy())
                cls_id = int(box.cls[0].cpu().numpy())

                if conf < self.conf_threshold:
                    continue

                # Translate local tile coords to global image coords
                x1g, y1g = x1 + col, y1 + row
                x2g, y2g = x2 + col, y2 + row

                # Georeference
                geo = self.georeference_box(x1g, y1g, x2g, y2g, batch.metadata)
                if geo is None:
                    continue
                bbox_wkt, lat, lon = geo

                # Compute detection datetime
                det_dt = self.compute_detection_datetime(y1g, y2g, batch.metadata)

                detections.append(Detection(
                    image_name=batch.metadata.image_name,
                    sensor_type=self.sensor_type,
                    xmin=float(x1g), ymin=float(y1g),
                    xmax=float(x2g), ymax=float(y2g),
                    class_id=cls_id,
                    confidence=conf,
                    bbox_wkt=bbox_wkt,
                    vessel_latitude=lat,
                    vessel_longitude=lon,
                    detection_datetime=det_dt,
                    image_capture_start_datetime=(
                        batch.metadata.start_time.isoformat()
                        if batch.metadata.start_time else None
                    ),
                    image_capture_end_datetime=(
                        batch.metadata.end_time.isoformat()
                        if batch.metadata.end_time else None
                    ),
                ))

        # Free GPU memory between batches
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return detections

    def process_folder(self, safe_folder: str) -> list[Detection]:
        """
        Full pipeline for a single SAFE folder:
        parse metadata → preprocess → run inference on all batches.
        """
        metadata = self.parse_metadata(safe_folder)
        batches = self.preprocess_image(safe_folder, metadata)

        all_detections: list[Detection] = []
        for batch in batches:
            all_detections.extend(self.run_inference(batch))

        return all_detections
