"""
False Positive / False Negative reduction filters.

Applies geometry-based sanity checks and soft-NMS to:
  - Reduce FPs: aspect ratio check, minimum area, vessel size plausibility
  - Reduce FNs: soft-NMS replaces hard NMS so closely-spaced real ships
    (convoys, flotillas) are preserved instead of being deleted by IoU overlap

All operations are label-free and work directly on Detection schema objects.
"""

from __future__ import annotations

import math

import numpy as np

from shared.schemas import Detection, SensorType
from inference.scoring.calibration_params import (
    ASPECT_RATIO_BOUNDS,
    MIN_PIXEL_AREA,
    MAX_SHIP_WIDTH_KM,
    SOFT_NMS_SIGMA,
    SOFT_NMS_MINIMAL_SCORE,
)


# ─────────────────────────────────────────
# Haversine helper (no pyproj dependency)
# ─────────────────────────────────────────
_R_EARTH_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two WGS-84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return 2 * _R_EARTH_KM * math.asin(math.sqrt(a))


class FPFNReducer:
    """
    Label-free filter pipeline for reducing False Positives and False Negatives.

    Filters applied in order:
      1. Aspect ratio sanity check
      2. Minimum pixel area check
      3. Vessel size geographic plausibility
      4. Soft-NMS (replaces hard NMS to preserve close real ships)

    Each detection that survives has its `fp_flags` list populated with
    human-readable reasons if it was *close to* being filtered, for transparency.
    """

    def filter(
        self,
        detections: list[Detection],
        sensor_type: SensorType,
    ) -> list[Detection]:
        """
        Apply all FP/FN reduction filters and return surviving detections.

        Args:
            detections: Raw detections from inference (already georeferenced).
            sensor_type: SAR or EO — determines filter thresholds.

        Returns:
            Filtered list with fp_flags populated on marginal detections.
        """
        if not detections:
            return detections

        after_geom = self._geometry_filter(detections, sensor_type)
        after_nms = self._soft_nms(after_geom, sensor_type)
        return after_nms

    # ------------------------------------------------------------------
    # Geometry filters (aspect ratio, area, plausibility)
    # ------------------------------------------------------------------
    def _geometry_filter(
        self, detections: list[Detection], sensor_type: SensorType
    ) -> list[Detection]:
        """Remove geometrically implausible detections and flag marginal ones."""
        ar_lo, ar_hi = ASPECT_RATIO_BOUNDS[sensor_type]
        min_area = MIN_PIXEL_AREA[sensor_type]
        kept: list[Detection] = []

        for det in detections:
            flags: list[str] = list(det.fp_flags)

            w = det.xmax - det.xmin
            h = det.ymax - det.ymin

            # 1. Aspect ratio
            if h < 1e-6:
                flags.append("degenerate_height")
                det = det.model_copy(update={"fp_flags": flags})
                # Zero height is definitely noise — skip
                continue
            ar = w / h
            if ar < ar_lo or ar > ar_hi:
                flags.append(f"aspect_ratio:{ar:.2f}_outside_[{ar_lo},{ar_hi}]")
                det = det.model_copy(update={"fp_flags": flags})
                continue  # FP — reject

            # 2. Minimum area
            area = w * h
            if area < min_area:
                flags.append(f"pixel_area:{area:.1f}<{min_area}")
                det = det.model_copy(update={"fp_flags": flags})
                continue  # FP — reject

            # 3. Geographic plausibility (using WKT bbox if available)
            plaus_ok, plaus_note = self._check_geographic_plausibility(det)
            if not plaus_ok:
                flags.append(plaus_note)
                det = det.model_copy(update={"fp_flags": flags})
                continue  # FP — reject

            if flags:
                det = det.model_copy(update={"fp_flags": flags})
            kept.append(det)

        return kept

    @staticmethod
    def _check_geographic_plausibility(det: Detection) -> tuple[bool, str]:
        """
        Estimate bounding box geographic extent from bbox_wkt polygon corners.
        Reject if width exceeds MAX_SHIP_WIDTH_KM (implausible for a vessel).
        Returns (passes, reason_if_failed).
        """
        if not det.bbox_wkt:
            return True, ""  # No WKT — can't check, pass through

        try:
            # Parse simple POLYGON((lon lat, ...)) WKT without shapely
            coords_str = det.bbox_wkt.replace("POLYGON((", "").replace("))", "").strip()
            pairs = [p.strip().split() for p in coords_str.split(",")]
            coords = [(float(p[0]), float(p[1])) for p in pairs if len(p) == 2]

            if len(coords) < 3:
                return True, ""

            lats = [c[1] for c in coords]
            lons = [c[0] for c in coords]

            # Width = east-west haversine distance
            width_km = _haversine_km(min(lats), min(lons), min(lats), max(lons))
            if width_km > MAX_SHIP_WIDTH_KM:
                return False, f"geo_width:{width_km:.2f}km>MAX_{MAX_SHIP_WIDTH_KM}km"

        except Exception:
            pass  # If parsing fails, don't reject

        return True, ""

    # ------------------------------------------------------------------
    # Soft-NMS
    # ------------------------------------------------------------------
    def _soft_nms(
        self, detections: list[Detection], sensor_type: SensorType
    ) -> list[Detection]:
        """
        Apply Soft Non-Maximum Suppression using Gaussian decay.

        Unlike hard NMS (which deletes overlapping boxes), soft-NMS decays
        the calibrated_confidence of overlapping boxes exponentially:
          score_i *= exp(-IoU(i, j)² / sigma)

        This preserves closely-spaced real ships (convoys, flotillas) that
        hard NMS would incorrectly delete — directly reducing False Negatives.

        Detections whose decayed calibrated_confidence falls below
        SOFT_NMS_MINIMAL_SCORE are removed (this threshold is intentionally
        very low: 0.05, so only truly suppressed duplicates are dropped).
        """
        if len(detections) <= 1:
            return detections

        sigma = SOFT_NMS_SIGMA[sensor_type]

        # Work with numpy for speed
        boxes = np.array(
            [[d.xmin, d.ymin, d.xmax, d.ymax] for d in detections],
            dtype=np.float64,
        )
        scores = np.array(
            [d.calibrated_confidence for d in detections], dtype=np.float64
        )

        n = len(detections)
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        areas = np.maximum(areas, 1e-8)

        for i in range(n):
            # For each box, decay all others based on IoU with the current max
            max_idx = int(np.argmax(scores[i:]) + i)
            if max_idx != i:
                boxes[[i, max_idx]] = boxes[[max_idx, i]]
                scores[[i, max_idx]] = scores[[max_idx, i]]
                detections[i], detections[max_idx] = detections[max_idx], detections[i]

            x1 = np.maximum(boxes[i + 1 :, 0], boxes[i, 0])
            y1 = np.maximum(boxes[i + 1 :, 1], boxes[i, 1])
            x2 = np.minimum(boxes[i + 1 :, 2], boxes[i, 2])
            y2 = np.minimum(boxes[i + 1 :, 3], boxes[i, 3])

            inter_w = np.maximum(0.0, x2 - x1)
            inter_h = np.maximum(0.0, y2 - y1)
            inter = inter_w * inter_h
            union = areas[i] + areas[i + 1 :] - inter
            iou = inter / np.maximum(union, 1e-8)

            # Gaussian decay: score *= exp(-iou² / sigma)
            decay = np.exp(-(iou**2) / sigma)
            scores[i + 1 :] *= decay

        # Reconstruct out — update calibrated_confidence with decayed scores
        result: list[Detection] = []
        for i, (det, new_score) in enumerate(zip(detections, scores)):
            if new_score < SOFT_NMS_MINIMAL_SCORE:
                continue  # Truly suppressed duplicate — drop
            updated = det.model_copy(update={"calibrated_confidence": float(new_score)})
            result.append(updated)

        return result
