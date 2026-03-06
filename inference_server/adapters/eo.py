"""
EO (Sentinel-2) sensor adapter.

Handles:
  - Reading RGB bands (B04, B03, B02) from S2 SAFE GRANULE/IMG_DATA
  - 512×512 patches with 8-bit conversion (reflectance / 10000)
  - CRS transform-based georeferencing via pyproj
  - Sensing-time XML + pushbroom velocity datetime estimation
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, Generator

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window
from shapely.geometry import Polygon

from shared.schemas import SensorType

from .base import ImageMetadata, PatchBatch, SensorAdapter


class EOAdapter(SensorAdapter):
    """Adapter for Sentinel-2 electro-optical imagery."""

    sensor_type = SensorType.EO
    model_path = os.path.join("inference_server", "models", "eo_best.pt")
    patch_size = 512
    stride = 512 - 32  # overlap of 32px
    conf_threshold = 0.80
    batch_size = 32
    imgsz = 512

    SENSOR_VELOCITY_KMS = 7.5   # Sentinel-2 spacecraft speed km/s
    GRANULE_SIZE_KM = 100.0     # approximate granule size km

    def __init__(self):
        super().__init__()
        self._sensing_cache: dict[str, tuple[Optional[datetime], Optional[int]]] = {}

    # ----- Folder discovery -----
    def find_image_folders(self, root_dir: str) -> list[str]:
        if not os.path.isdir(root_dir):
            return []
        return [
            os.path.join(root_dir, f)
            for f in sorted(os.listdir(root_dir))
            if os.path.isdir(os.path.join(root_dir, f)) and f.startswith("S2")
        ]

    # ----- Metadata parsing -----
    def parse_metadata(self, safe_folder: str) -> ImageMetadata:
        folder_name = os.path.basename(os.path.normpath(safe_folder))
        parts = folder_name.split("_")
        start_time, end_time = None, None
        if len(parts) >= 3:
            try:
                start_time = datetime.strptime(parts[2], "%Y%m%dT%H%M%S")
                end_time = start_time
            except ValueError:
                pass

        meta = ImageMetadata(
            safe_folder=safe_folder,
            image_name=folder_name,
            sensor_type=SensorType.EO,
            start_time=start_time,
            end_time=end_time,
        )

        # Find IMG_DATA and read transform/crs/dimensions
        img_data_path = self._find_img_data_path(safe_folder)
        if img_data_path:
            band_files = self._get_band_files(img_data_path)
            if band_files.get("B04"):
                try:
                    with rasterio.open(band_files["B04"]) as src:
                        meta.width = src.width
                        meta.height = src.height
                        meta.extra["transform"] = src.transform
                        meta.extra["crs"] = src.crs
                except Exception:
                    pass
            meta.extra["img_data_path"] = img_data_path
            meta.extra["band_files"] = band_files

        # Cache sensing time + image height
        self._cache_sensing_info(safe_folder, folder_name, meta)

        return meta

    # ----- Image preprocessing -----
    def preprocess_image(
        self, safe_folder: str, metadata: ImageMetadata
    ) -> Generator[PatchBatch, None, None]:
        band_files = metadata.extra.get("band_files", {})
        if not all(band_files.get(b) for b in ("B04", "B03", "B02")):
            return []

        height = metadata.height
        width = metadata.width
        if height == 0 or width == 0:
            return []

        # No longer accumulating into a list

        for row in range(0, height, self.stride):
            for col in range(0, width, self.stride):
                patch = self._read_patch_from_bands(
                    band_files, col, row, self.patch_size
                )
                if patch is None:
                    continue

                # Convert HWC uint8 to CHW float32
                tile_chw = np.transpose(patch, (2, 0, 1)).astype(np.float32)
                batch_tiles.append(tile_chw)
                batch_positions.append((row, col))

                if len(batch_tiles) >= self.batch_size:
                    yield PatchBatch(
                        tiles=np.stack(batch_tiles, axis=0),
                        positions=batch_positions,
                        metadata=metadata,
                    )
                    batch_tiles = []
                    batch_positions = []

        if batch_tiles:
            yield PatchBatch(
                tiles=np.stack(batch_tiles, axis=0),
                positions=batch_positions,
                metadata=metadata,
            )

    # ----- Georeferencing -----
    def georeference_box(
        self, x1: float, y1: float, x2: float, y2: float, metadata: ImageMetadata
    ) -> Optional[tuple[str, float, float]]:
        transform = metadata.extra.get("transform")
        crs = metadata.extra.get("crs")
        if transform is None or crs is None:
            return None

        try:
            corners_pixel = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            coords = [
                rasterio.transform.xy(transform, y, x, offset="center")
                for x, y in corners_pixel
            ]
            transformer = Transformer.from_crs(
                crs.to_string(), "EPSG:4326", always_xy=True
            )
            latlon_coords = [transformer.transform(x, y) for x, y in coords]
            poly = Polygon(latlon_coords)
            centroid = poly.centroid
            return poly.wkt, float(centroid.y), float(centroid.x)
        except Exception:
            return None

    # ----- Detection datetime -----
    def compute_detection_datetime(
        self, ymin: float, ymax: float, metadata: ImageMetadata
    ) -> Optional[str]:
        cached = self._sensing_cache.get(metadata.image_name)
        if cached is None:
            return None
        sensing_time, img_height = cached
        if sensing_time is None or img_height is None:
            return None

        line_idx = 0.5 * (ymin + ymax)
        frac = min(max(line_idx / img_height, 0), 1)
        granule_duration = self.GRANULE_SIZE_KM / self.SENSOR_VELOCITY_KMS
        delta_seconds = frac * granule_duration
        det_time = sensing_time + timedelta(seconds=delta_seconds)
        return det_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ================================================================
    # Private helpers
    # ================================================================
    @staticmethod
    def _find_img_data_path(safe_folder: str) -> Optional[str]:
        granule_path = os.path.join(safe_folder, "GRANULE")
        if not os.path.exists(granule_path):
            return None
        for d in os.listdir(granule_path):
            img_data = os.path.join(granule_path, d, "IMG_DATA")
            if os.path.exists(img_data):
                return img_data
        return None

    @staticmethod
    def _get_band_files(img_data_path: str) -> dict[str, Optional[str]]:
        bands: dict[str, Optional[str]] = {"B04": None, "B03": None, "B02": None}
        for f in os.listdir(img_data_path):
            for band_name in bands:
                if f.endswith(f"_{band_name}.jp2"):
                    bands[band_name] = os.path.join(img_data_path, f)
        return bands

    @staticmethod
    def _read_patch_from_bands(
        band_files: dict, col: int, row: int, patch_size: int
    ) -> Optional[np.ndarray]:
        window = Window(col, row, patch_size, patch_size)
        try:
            with rasterio.open(band_files["B04"]) as src:
                r = src.read(1, window=window).astype(np.float32)
            with rasterio.open(band_files["B03"]) as src:
                g = src.read(1, window=window).astype(np.float32)
            with rasterio.open(band_files["B02"]) as src:
                b = src.read(1, window=window).astype(np.float32)
        except Exception:
            return None

        h, w = r.shape
        if h < patch_size or w < patch_size:
            r_p = np.zeros((patch_size, patch_size), dtype=np.float32)
            g_p = np.zeros((patch_size, patch_size), dtype=np.float32)
            b_p = np.zeros((patch_size, patch_size), dtype=np.float32)
            r_p[:h, :w] = r
            g_p[:h, :w] = g
            b_p[:h, :w] = b
            r, g, b = r_p, g_p, b_p

        r_8 = np.clip(r / 10000.0, 0, 1) * 255
        g_8 = np.clip(g / 10000.0, 0, 1) * 255
        b_8 = np.clip(b / 10000.0, 0, 1) * 255

        return np.dstack([r_8, g_8, b_8]).astype(np.uint8)

    def _cache_sensing_info(
        self, safe_folder: str, folder_name: str, meta: ImageMetadata
    ):
        """Parse sensing time from MTD_TL.xml and cache it."""
        if folder_name in self._sensing_cache:
            return

        granule_folder = self._find_granule_folder(safe_folder)
        sensing_time, img_height = None, None

        if granule_folder:
            mtd_path = os.path.join(granule_folder, "MTD_TL.xml")
            if os.path.exists(mtd_path):
                sensing_time = self._parse_sensing_time(mtd_path)
                img_height = meta.height if meta.height > 0 else 10980

        self._sensing_cache[folder_name] = (sensing_time, img_height)

    @staticmethod
    def _find_granule_folder(safe_folder: str) -> Optional[str]:
        granule_dir = os.path.join(safe_folder, "GRANULE")
        if not os.path.isdir(granule_dir):
            return None
        entries = [
            os.path.join(granule_dir, d)
            for d in os.listdir(granule_dir)
            if os.path.isdir(os.path.join(granule_dir, d))
        ]
        return entries[0] if entries else None

    @staticmethod
    def _parse_sensing_time(mtd_tl_xml_path: str) -> Optional[datetime]:
        try:
            tree = ET.parse(mtd_tl_xml_path)
            root = tree.getroot()

            sensing_elem = root.find("SENSING_TIME")
            if sensing_elem is None:
                for elem in root.iter():
                    if elem.tag.endswith("SENSING_TIME"):
                        sensing_elem = elem
                        break

            if sensing_elem is None or not sensing_elem.text:
                return None

            text = sensing_elem.text.strip()
            if text.endswith("Z"):
                text = text[:-1]
            return datetime.fromisoformat(text)
        except Exception:
            return None
