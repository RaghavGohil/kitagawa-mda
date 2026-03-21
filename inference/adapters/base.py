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

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Generator

import numpy as np
import torch
from ultralytics import YOLO

from shared.schemas import Detection, SensorType
from shared.utils import check_resources
from inference.scoring.confidence import ConfidenceCalibrator
from inference.scoring.situation import SituationScorer


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

    tiles: np.ndarray  # shape [B, 3, H, W], float32
    positions: list[tuple[int, int]]  # (row, col) per tile
    metadata: ImageMetadata  # source image metadata


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
        # Shared scoring components — instantiated once per adapter instance
        self._calibrator = ConfidenceCalibrator()
        self._situation_scorer = SituationScorer()

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
    def preprocess_image(
        self, safe_folder: str, metadata: ImageMetadata
    ) -> Generator[PatchBatch, None, None]:
        """
        Read the image from a SAFE folder and generate patch batches.
        Yields PatchBatch objects one by one for run_inference().
        """
        ...

    @abstractmethod
    def georeference_box(
        self, x1: float, y1: float, x2: float, y2: float, metadata: ImageMetadata
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

    def run_inference(self, batch: PatchBatch) -> list[Detection]:
        """
        Run YOLO inference on a batch and return georeferenced, scored detections.

        Pipeline per batch:
          1. YOLO inference (raw confidence scores)
          2. Georeference each box
          3. Build Detection objects
          4. Apply temperature-scaled confidence calibration (dataset-free)
          5. Compute situation score (context-aware adjustment)
          6. Fuse into final_score = clip(calibrated + situation, 0, 1)
        """
        tiles = torch.tensor(batch.tiles, dtype=torch.float32, device=self._device)

        results = self.model.predict(
            tiles,
            imgsz=self.imgsz,
            conf=self.conf_threshold,
            verbose=False,
            device=self._device,
        )

        raw_detections: list[Detection] = []

        for idx, res in enumerate(results):
            row, col = batch.positions[idx]
            for box in res.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
                conf = float(box.conf[0].cpu().numpy())
                cls_id = int(box.cls[0].cpu().numpy())

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

                raw_detections.append(
                    Detection(
                        image_name=batch.metadata.image_name,
                        sensor_type=self.sensor_type,
                        xmin=float(x1g),
                        ymin=float(y1g),
                        xmax=float(x2g),
                        ymax=float(y2g),
                        class_id=cls_id,
                        confidence=conf,
                        bbox_wkt=bbox_wkt,
                        vessel_latitude=lat,
                        vessel_longitude=lon,
                        detection_datetime=det_dt,
                        image_capture_start_datetime=(
                            batch.metadata.start_time.isoformat()
                            if batch.metadata.start_time
                            else None
                        ),
                        image_capture_end_datetime=(
                            batch.metadata.end_time.isoformat()
                            if batch.metadata.end_time
                            else None
                        ),
                    )
                )

        # ── Step 2: Batch confidence calibration (temperature scaling) ────────
        if raw_detections:
            raw_scores = [d.confidence for d in raw_detections]
            calibrated_scores = self._calibrator.calibrate_batch(
                raw_scores, self.sensor_type
            )

            # Adaptive threshold: data-driven cutoff from this image's distribution
            threshold = self._calibrator.adaptive_threshold(calibrated_scores)

            scored_detections: list[Detection] = []
            for det, cal_conf in zip(raw_detections, calibrated_scores):
                if cal_conf < threshold:
                    continue  # Below adaptive threshold — skip

                # ── Step 3: Situation score ─────────────────────────────────
                sit_score = self._situation_scorer.score(det, self.sensor_type)
                final = self._situation_scorer.compute_final_score(cal_conf, sit_score)

                scored_detections.append(
                    det.model_copy(
                        update={
                            "calibrated_confidence": cal_conf,
                            "situation_score": sit_score,
                            "final_score": final,
                        }
                    )
                )
        else:
            scored_detections = []

        # Free GPU memory between batches
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return scored_detections

    def process_folder(self, safe_folder: str) -> list[Detection]:
        """
        Full pipeline for a single SAFE folder:
        parse metadata → preprocess → run inference on all batches.
        """
        metadata = self.parse_metadata(safe_folder)
        all_detections: list[Detection] = []

        # Generator handles one batch at a time to minimize memory
        for batch in self.preprocess_image(safe_folder, metadata):
            # Proactive resource check before each batch
            ok, msg = check_resources(min_disk_gb=0.5, max_mem_pct=95.0)
            if not ok:
                print(f"[Inference] Aborting: {msg}")
                break

            all_detections.extend(self.run_inference(batch))

        return all_detections
