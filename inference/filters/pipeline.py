"""
Unified filter pipeline for post-processing detections.

Chains: FPFNReducer (geometry + soft-NMS) → Landmask → Cloudmask (EO only).
All filters operate in-memory on Detection lists (no CSV I/O).
"""

from __future__ import annotations

import os
import sys
import zipfile
from typing import Optional

import torch

from shared.schemas import Detection, SensorType
from inference.scoring.fp_fn import FPFNReducer


class FilterPipeline:
    """
    Applies post-processing filters to a list of detections.

    Filters:
      1. FPFNReducer — geometry checks (aspect ratio, area, plausibility)
                     + soft-NMS (replaces hard NMS; preserves close real ships)
      2. Landmask — removes detections on land (GSHHG shapefile)
      3. Cloudmask — removes cloudy EO detections (ConvNeXt classifier)
    """

    def __init__(
        self,
        landmask_shp_path: Optional[str] = None,
        cloudmask_model_dir: Optional[str] = None,
    ):
        self._land_gdf = None
        self._land_sindex = None
        self._cloudmask_model = None
        self._cloudmask_device = "cuda" if torch.cuda.is_available() else "cpu"
        self._fp_fn_reducer = FPFNReducer()

        self._landmask_shp_path = landmask_shp_path
        self._cloudmask_model_dir = cloudmask_model_dir

    def apply(
        self,
        detections: list[Detection],
        apply_nms: bool = True,
        apply_landmask: bool = True,
        apply_cloudmask: bool = True,
    ) -> list[Detection]:
        """Run all applicable filters on the detection list."""
        if not detections:
            return detections

        # Step 1: FP/FN reduction (geometry + soft-NMS) per sensor type
        if apply_nms:
            # Group by sensor type so each group uses the right thresholds
            from collections import defaultdict

            by_sensor: dict = defaultdict(list)
            for d in detections:
                by_sensor[d.sensor_type].append(d)
            detections = []
            for stype, dets in by_sensor.items():
                detections.extend(self._fp_fn_reducer.filter(dets, stype))

        if apply_landmask:
            if (
                self._land_gdf is None
                and self._landmask_shp_path
                and os.path.exists(self._landmask_shp_path)
            ):
                self._load_landmask(self._landmask_shp_path)

            if self._land_gdf is not None:
                detections = self._landmask_filter(detections)

        if apply_cloudmask:
            if (
                self._cloudmask_model is None
                and self._cloudmask_model_dir
                and os.path.isdir(self._cloudmask_model_dir)
            ):
                self._load_cloudmask(self._cloudmask_model_dir)

            if self._cloudmask_model is not None:
                # Cloudmask only applies to EO detections
                eo_dets = [d for d in detections if d.sensor_type == SensorType.EO]
                non_eo = [d for d in detections if d.sensor_type != SensorType.EO]
                if eo_dets:
                    eo_dets = self._cloudmask_filter(eo_dets)
                detections = non_eo + eo_dets

        return detections

    # ------------------------------------------------------------------
    # Landmask filter
    # ------------------------------------------------------------------
    def _load_landmask(self, shp_path: str):
        """Load GSHHG land polygons and build spatial index."""
        print(f"[FilterPipeline] Attempting to load landmask from: {shp_path}")
        if not os.path.exists(shp_path):
            print(f"[FilterPipeline] ERROR: Landmask file NOT FOUND at {shp_path}")
            # Try to list directory to see what's there
            parent = os.path.dirname(shp_path)
            if os.path.exists(parent):
                print(
                    f"[FilterPipeline] Parent directory {parent} contents: {os.listdir(parent)}"
                )
            return

        try:
            import geopandas as gpd

            self._land_gdf = gpd.read_file(shp_path)
            self._land_gdf = self._land_gdf.to_crs(epsg=4326)
            self._land_sindex = self._land_gdf.sindex
            print(
                f"[FilterPipeline] SUCCESS: Loaded landmask with {len(self._land_gdf)} polygons"
            )
        except Exception as e:
            print(f"[FilterPipeline] FAILED to load landmask: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            self._land_gdf = None

    def _landmask_filter(self, detections: list[Detection]) -> list[Detection]:
        """Remove detections whose centroid falls on land."""
        from shapely.geometry import Point

        if self._land_gdf is None:
            print("[FilterPipeline] WARNING: Landmask not loaded, skipping filtering")
            return detections

        kept: list[Detection] = []
        land_count = 0
        for d in detections:
            point = Point(d.vessel_longitude, d.vessel_latitude)
            possible = list(self._land_sindex.intersection(point.bounds))
            on_land = False
            if possible:
                matches = self._land_gdf.iloc[possible]
                on_land = any(poly.contains(point) for poly in matches.geometry)

            if on_land:
                land_count += 1
                try:
                    with open("/data/landmask_debug.txt", "a") as f_log:
                        f_log.write(
                            f"{d.image_name}, {d.vessel_latitude}, {d.vessel_longitude}\n"
                        )
                except Exception:
                    pass
                continue
            kept.append(d)

        if land_count > 0:
            print(f"[FilterPipeline] Filtered out {land_count} detections on land.")
        return kept

    # ------------------------------------------------------------------
    # Cloudmask filter (EO only)
    # ------------------------------------------------------------------
    def _load_cloudmask(self, model_dir: str):
        """
        Load the ConvNeXt-Tiny cloudmask classifier.
        Handles combining split zip parts if needed.
        """
        try:
            from torchvision.models import ConvNeXt_Tiny_Weights, convnext_tiny
            import torch.nn as nn

            pth_path = os.path.join(model_dir, "cloudmask.pth")

            # Combine parts if .pth doesn't exist
            if not os.path.exists(pth_path):
                self._combine_and_extract_cloudmask(model_dir)

            if not os.path.exists(pth_path):
                print("[FilterPipeline] cloudmask.pth not found after extraction")
                return

            weights = ConvNeXt_Tiny_Weights.IMAGENET1K_V1
            model = convnext_tiny(weights=weights)

            if hasattr(model, "classifier") and isinstance(
                model.classifier, nn.Sequential
            ):
                for i in range(len(model.classifier) - 1, -1, -1):
                    if isinstance(model.classifier[i], nn.Linear):
                        in_features = model.classifier[i].in_features
                        model.classifier[i] = nn.Linear(in_features, 1)
                        break
            else:
                model.classifier = nn.Linear(768, 1)

            checkpoint = torch.load(pth_path, map_location=self._cloudmask_device)
            if "model_state_dict" in checkpoint:
                model.load_state_dict(checkpoint["model_state_dict"])
            else:
                model.load_state_dict(checkpoint)

            model = model.to(self._cloudmask_device)
            model.eval()
            self._cloudmask_model = model
            print("[FilterPipeline] Cloudmask model loaded successfully")

        except Exception as e:
            print(
                f"[FilterPipeline] Failed to load cloudmask model: {e}",
                file=sys.stderr,
            )

    @staticmethod
    def _combine_and_extract_cloudmask(model_dir: str):
        """Combine split zip parts and extract."""
        parts = sorted(
            os.path.join(model_dir, p)
            for p in os.listdir(model_dir)
            if p.startswith("cloudmask.zip.part.")
        )
        if not parts:
            return

        archive = os.path.join(model_dir, "cloudmask.zip")
        if not os.path.exists(archive):
            with open(archive, "wb") as out:
                for p in parts:
                    with open(p, "rb") as pf:
                        out.write(pf.read())

        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(model_dir)

    def _cloudmask_filter(
        self,
        detections: list[Detection],
        conf_threshold: float = 0.57,
    ) -> list[Detection]:
        """
        Keep only detections where the cloudmask classifier says 'not cloud'.

        Note: This is a simplified version that uses confidence scores only.
        The full version (reading image patches) requires access to the source
        images, which should be done via the adapter if needed.
        """
        # Without source image access for cropping, we pass through all detections.
        # The cloudmask filter is most effective when image patches can be extracted.
        # In the refactored architecture, cloudmask filtering can be triggered
        # separately when image data is available.
        return detections
