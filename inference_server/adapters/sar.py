"""
SAR (Sentinel-1) sensor adapter.

Handles:
  - Reading VV-polarization TIFF from S1 SAFE measurement/ directory
  - 1024×1024 patches with min-max normalization
  - GCP-based georeferencing (rasterio)
  - Calibration XML-based per-line datetime interpolation
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import rasterio
from rasterio import warp as rio_warp
from rasterio.windows import Window
from shapely.geometry import Polygon

from shared.schemas import SensorType

from .base import ImageMetadata, PatchBatch, SensorAdapter


class SARAdapter(SensorAdapter):
    """Adapter for Sentinel-1 SAR imagery (GRD, VV polarization)."""

    sensor_type = SensorType.SAR
    model_path = os.path.join("inference_server", "models", "sar_best.pt")
    patch_size = 1024
    stride = 1024
    conf_threshold = 0.50
    batch_size = 32
    imgsz = 128

    def __init__(self):
        super().__init__()
        self._calib_cache: dict[str, Optional[callable]] = {}

    # ----- Folder discovery -----
    def find_image_folders(self, root_dir: str) -> list[str]:
        if not os.path.isdir(root_dir):
            return []
        return [
            os.path.join(root_dir, f)
            for f in sorted(os.listdir(root_dir))
            if os.path.isdir(os.path.join(root_dir, f)) and f.startswith("S1")
        ]

    # ----- Metadata parsing -----
    def parse_metadata(self, safe_folder: str) -> ImageMetadata:
        folder_name = os.path.basename(safe_folder)
        parts = folder_name.split("_")
        start_time, end_time = None, None
        if len(parts) >= 7:
            try:
                start_time = datetime.strptime(parts[4], "%Y%m%dT%H%M%S")
                end_time = datetime.strptime(parts[5], "%Y%m%dT%H%M%S")
            except Exception:
                pass

        meta = ImageMetadata(
            safe_folder=safe_folder,
            image_name=folder_name,
            sensor_type=SensorType.SAR,
            start_time=start_time,
            end_time=end_time,
        )

        # Pre-compute GCP transform and cache in extra
        img_file = self._find_vv_tiff(safe_folder)
        if img_file:
            try:
                with rasterio.open(img_file) as src:
                    meta.width = src.width
                    meta.height = src.height
                    gcps, gcps_crs = src.get_gcps()
                    if gcps:
                        gcps_transform = rasterio.transform.from_gcps(gcps)
                        need_transform = True
                        try:
                            if gcps_crs.to_epsg() == 4326:
                                need_transform = False
                        except Exception:
                            pass
                        meta.extra["gcps_transform"] = gcps_transform
                        meta.extra["gcps_crs"] = gcps_crs
                        meta.extra["need_transform"] = need_transform
                        meta.extra["img_file"] = img_file
            except Exception:
                pass

        # Build line→time interpolator
        self._ensure_calib_interpolator(safe_folder, folder_name)

        return meta

    # ----- Image preprocessing -----
    def preprocess_image(
        self, safe_folder: str, metadata: ImageMetadata
    ) -> list[PatchBatch]:
        img_file = metadata.extra.get("img_file")
        if not img_file:
            img_file = self._find_vv_tiff(safe_folder)
        if img_file is None:
            return []

        batches: list[PatchBatch] = []

        with rasterio.open(img_file) as src:
            width, height = src.width, src.height

            batch_tiles: list[np.ndarray] = []
            batch_positions: list[tuple[int, int]] = []

            for row in range(0, height, self.stride):
                for col in range(0, width, self.stride):
                    w_win = min(self.patch_size, width - col)
                    h_win = min(self.patch_size, height - row)

                    patch = src.read(
                        1, window=Window(col, row, w_win, h_win)
                    ).astype(np.float32)

                    # Pad to patch_size
                    if patch.shape[0] != self.patch_size or patch.shape[1] != self.patch_size:
                        padded = np.zeros(
                            (self.patch_size, self.patch_size), dtype=np.float32
                        )
                        padded[: patch.shape[0], : patch.shape[1]] = patch
                        patch = padded

                    # Min-max normalize
                    pmin = float(np.nanmin(patch))
                    pmax = float(np.nanmax(patch))
                    if pmax > pmin:
                        patch = (patch - pmin) / (pmax - pmin)
                    else:
                        patch = np.zeros_like(patch, dtype=np.float32)

                    # Stack to 3 channels CHW
                    tile_chw = np.stack([patch, patch, patch], axis=0).astype(
                        np.float32
                    )

                    batch_tiles.append(tile_chw)
                    batch_positions.append((row, col))

                    if len(batch_tiles) >= self.batch_size:
                        batches.append(
                            PatchBatch(
                                tiles=np.stack(batch_tiles, axis=0),
                                positions=batch_positions,
                                metadata=metadata,
                            )
                        )
                        batch_tiles = []
                        batch_positions = []

            # Leftover
            if batch_tiles:
                batches.append(
                    PatchBatch(
                        tiles=np.stack(batch_tiles, axis=0),
                        positions=batch_positions,
                        metadata=metadata,
                    )
                )

        return batches

    # ----- Georeferencing -----
    def georeference_box(
        self, x1: float, y1: float, x2: float, y2: float, metadata: ImageMetadata
    ) -> Optional[tuple[str, float, float]]:
        gcps_transform = metadata.extra.get("gcps_transform")
        gcps_crs = metadata.extra.get("gcps_crs")
        need_transform = metadata.extra.get("need_transform", True)

        if gcps_transform is None:
            return None

        try:
            corners = [
                self._pixel_to_lonlat(gcps_transform, gcps_crs, need_transform, x1, y1),
                self._pixel_to_lonlat(gcps_transform, gcps_crs, need_transform, x2, y1),
                self._pixel_to_lonlat(gcps_transform, gcps_crs, need_transform, x2, y2),
                self._pixel_to_lonlat(gcps_transform, gcps_crs, need_transform, x1, y2),
            ]
            poly = Polygon(corners)
            centroid = poly.centroid
            return poly.wkt, float(centroid.y), float(centroid.x)
        except Exception:
            return None

    # ----- Detection datetime -----
    def compute_detection_datetime(
        self, ymin: float, ymax: float, metadata: ImageMetadata
    ) -> Optional[str]:
        interp = self._calib_cache.get(metadata.image_name)
        if interp is None:
            return None
        try:
            line_idx = 0.5 * (ymin + ymax)
            return interp(line_idx)
        except Exception:
            return None

    # ================================================================
    # Private helpers
    # ================================================================
    @staticmethod
    def _find_vv_tiff(safe_folder: str) -> Optional[str]:
        meas_path = os.path.join(safe_folder, "measurement")
        if not os.path.isdir(meas_path):
            return None
        for f in os.listdir(meas_path):
            if f.lower().endswith(".tiff") and "vv" in f.lower():
                return os.path.join(meas_path, f)
        return None

    @staticmethod
    def _pixel_to_lonlat(gcps_transform, gcps_crs, need_transform, x, y):
        lon, lat = gcps_transform * (x, y)
        if need_transform:
            xs, ys = rio_warp.transform(gcps_crs, "EPSG:4326", [lon], [lat])
            lon, lat = xs[0], ys[0]
        return float(lon), float(lat)

    def _ensure_calib_interpolator(self, safe_folder: str, safe_name: str):
        """Build and cache the line→time interpolator from calibration XML."""
        if safe_name in self._calib_cache:
            return

        annot_calib_dir = os.path.join(safe_folder, "annotation", "calibration")
        if not os.path.isdir(annot_calib_dir):
            self._calib_cache[safe_name] = None
            return

        calib_xml = None
        for f in os.listdir(annot_calib_dir):
            if (
                f.lower().startswith("calibration-s1a-iw-grd-vv-")
                and f.lower().endswith(".xml")
            ):
                calib_xml = os.path.join(annot_calib_dir, f)
                break

        if calib_xml is None:
            self._calib_cache[safe_name] = None
            return

        try:
            tree = ET.parse(calib_xml)
        except Exception as e:
            print(f"[WARN] Failed to parse calibration XML: {e}", file=sys.stderr)
            self._calib_cache[safe_name] = None
            return

        root = tree.getroot()
        ns = {}
        if "}" in root.tag:
            ns["s1"] = root.tag.split("}")[0].strip("{")

        lines, times = [], []
        for cv in root.findall(
            ".//calibrationVectorList/calibrationVector", ns
        ):
            az_el = cv.find("azimuthTime", ns)
            line_el = cv.find("line", ns)
            if az_el is None or line_el is None:
                continue
            try:
                t = datetime.fromisoformat(az_el.text)
                num_l = int(line_el.text)
            except Exception:
                continue
            lines.append(num_l)
            times.append(t)

        if len(lines) < 2:
            self._calib_cache[safe_name] = None
            return

        order = np.argsort(lines)
        lines_arr = np.array(lines, dtype=np.float64)[order]
        times_sorted = [times[i] for i in order]

        base = times_sorted[0]
        time_seconds = np.array(
            [(t - base).total_seconds() for t in times_sorted], dtype=np.float64
        )

        def line_to_time(line_idx_float: float) -> str:
            num_l = float(line_idx_float)
            if num_l <= lines_arr[0]:
                dt_sec = time_seconds[0]
            elif num_l >= lines_arr[-1]:
                dt_sec = time_seconds[-1]
            else:
                idx = np.searchsorted(lines_arr, num_l)
                l1, l2 = lines_arr[idx - 1], lines_arr[idx]
                t1, t2 = time_seconds[idx - 1], time_seconds[idx]
                dt_sec = t1 if l2 == l1 else t1 + (num_l - l1) / (l2 - l1) * (t2 - t1)

            dt = timedelta(seconds=float(dt_sec))
            t_interp = base + dt
            return t_interp.strftime("%Y-%m-%dT%H:%M:%SZ")

        self._calib_cache[safe_name] = line_to_time
