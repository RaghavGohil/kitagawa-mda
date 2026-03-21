"""
Unit tests for the inference scoring package.

Tests cover:
  - ConfidenceCalibrator: temperature scaling, normalization, adaptive Otsu threshold
  - FPFNReducer: aspect ratio, area, plausibility filters, soft-NMS
  - SituationScorer: time-of-day, zone, and sensor context factors

Run with:
  python -m pytest inference/tests/test_scoring.py -v
"""

from __future__ import annotations

import math
import pytest

from shared.schemas import Detection, SensorType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_detection(
    confidence: float = 0.75,
    xmin: float = 100.0,
    ymin: float = 100.0,
    xmax: float = 200.0,
    ymax: float = 150.0,
    lat: float = 35.0,
    lon: float = -70.0,
    sensor_type: SensorType = SensorType.SAR,
    detection_datetime: str = "2024-06-15T10:00:00Z",
    bbox_wkt: str = "POLYGON((-70.1 34.9, -70.0 34.9, -70.0 35.0, -70.1 35.0, -70.1 34.9))",
) -> Detection:
    return Detection(
        image_name="TEST_IMAGE",
        sensor_type=sensor_type,
        xmin=xmin,
        ymin=ymin,
        xmax=xmax,
        ymax=ymax,
        confidence=confidence,
        bbox_wkt=bbox_wkt,
        vessel_latitude=lat,
        vessel_longitude=lon,
        detection_datetime=detection_datetime,
    )


# ===========================================================================
# ConfidenceCalibrator tests
# ===========================================================================
class TestConfidenceCalibrator:
    def setup_method(self):
        from inference.scoring.confidence import ConfidenceCalibrator

        self.cal = ConfidenceCalibrator()

    def test_calibrate_batch_output_bounds(self):
        """Calibrated scores must be in [0, 1]."""
        raw = [0.3, 0.5, 0.6, 0.8, 0.9]
        out = self.cal.calibrate_batch(raw, SensorType.SAR)
        assert len(out) == len(raw)
        for s in out:
            assert 0.0 <= s <= 1.0, f"Score {s} out of bounds"

    def test_calibrate_batch_monotonic(self):
        """Higher raw scores should still rank higher after calibration."""
        raw = [0.3, 0.5, 0.7, 0.9]
        out = self.cal.calibrate_batch(raw, SensorType.SAR)
        for i in range(len(out) - 1):
            assert out[i] <= out[i + 1], "Calibration must preserve ranking"

    def test_max_calibrated_is_one(self):
        """After batch normalization, max should be 1.0."""
        raw = [0.4, 0.55, 0.7, 0.85]
        out = self.cal.calibrate_batch(raw, SensorType.EO)
        assert abs(max(out) - 1.0) < 1e-6, f"Max should be 1.0, got {max(out)}"

    def test_empty_batch(self):
        """Empty input returns empty output."""
        out = self.cal.calibrate_batch([], SensorType.SAR)
        assert out == []

    def test_sar_softer_than_eo(self):
        """SAR (T=1.5) should produce lower calibrated score than EO (T=1.3) for same raw."""
        raw = [0.7]
        sar_out = self.cal.calibrate_single(0.7, SensorType.SAR)
        eo_out = self.cal.calibrate_single(0.7, SensorType.EO)
        # SAR has higher temperature → softer → lower calibrated score
        assert sar_out < eo_out, f"SAR ({sar_out}) should be softer than EO ({eo_out})"

    def test_adaptive_threshold_few_detections(self):
        """Fewer than 3 detections → threshold is 0.0 (keep all)."""
        threshold = self.cal.adaptive_threshold([0.8])
        assert threshold == 0.0
        threshold2 = self.cal.adaptive_threshold([0.3, 0.7])
        assert threshold2 == 0.0

    def test_adaptive_threshold_bimodal(self):
        """Bimodal distribution: low cluster [0.1-0.2] and high cluster [0.8-0.9]."""
        scores = [0.10, 0.11, 0.12, 0.13, 0.80, 0.85, 0.88, 0.90]
        threshold = self.cal.adaptive_threshold(scores)
        # Otsu should find a split somewhere between 0.2 and 0.8
        assert 0.15 <= threshold <= 0.75, f"Threshold {threshold} not in expected range"

    def test_adaptive_threshold_range(self):
        """Threshold should always be clipped to [0.05, 0.80]."""
        # Uniform distribution
        scores = [float(i) / 10 for i in range(1, 11)]
        threshold = self.cal.adaptive_threshold(scores)
        assert 0.05 <= threshold <= 0.80


# ===========================================================================
# FPFNReducer tests
# ===========================================================================
class TestFPFNReducer:
    def setup_method(self):
        from inference.scoring.fp_fn import FPFNReducer

        self.reducer = FPFNReducer()

    def test_passes_valid_detection(self):
        """A well-shaped vessel detection should pass all geometry filters."""
        det = make_detection(xmin=0, ymin=0, xmax=200, ymax=80)  # AR=2.5
        result = self.reducer.filter([det], SensorType.EO)
        assert len(result) == 1

    def test_rejects_square_blob(self):
        """A perfectly square blob (AR=1.0) should NOT be rejected (1.0 is within bounds)."""
        # Aspect ratio bounds are [0.10, 10.0] for EO — 1.0 is within range
        det = make_detection(xmin=0, ymin=0, xmax=100, ymax=100)  # AR=1.0
        result = self.reducer.filter([det], SensorType.EO)
        assert len(result) == 1  # Square is still within bounds

    def test_rejects_extreme_aspect_ratio(self):
        """An extreme AR > 10 should be rejected."""
        det = make_detection(xmin=0, ymin=0, xmax=1000, ymax=50)  # AR = 20
        result = self.reducer.filter([det], SensorType.EO)
        assert len(result) == 0, "Extreme AR should be rejected as FP"

    def test_rejects_tiny_area(self):
        """A 4x4 pixel detection should be rejected for EO (min_area=64)."""
        det = make_detection(xmin=0, ymin=0, xmax=4, ymax=4)  # area=16 < 64
        result = self.reducer.filter([det], SensorType.EO)
        assert len(result) == 0, "Tiny area should be rejected as FP"

    def test_accepts_tiny_sar(self):
        """A 5x5 SAR detection (area=25 > 16) should pass the SAR area filter."""
        det = make_detection(xmin=0, ymin=0, xmax=5, ymax=5, sensor_type=SensorType.SAR)
        result = self.reducer.filter([det], SensorType.SAR)
        assert len(result) == 1

    def test_soft_nms_preserves_well_separated(self):
        """Two well-separated detections should both survive soft-NMS."""
        det1 = make_detection(xmin=0, ymin=0, xmax=100, ymax=50, lat=35.0)
        det2 = make_detection(
            xmin=500, ymin=500, xmax=600, ymax=550, lat=36.5, lon=-69.0
        )
        det1 = det1.model_copy(update={"calibrated_confidence": 0.9})
        det2 = det2.model_copy(update={"calibrated_confidence": 0.8})
        result = self.reducer.filter([det1, det2], SensorType.SAR)
        assert len(result) == 2, "Non-overlapping detections should both survive"

    def test_soft_nms_decays_overlapping(self):
        """Nearly identical overlapping boxes: lower-scored one should have decayed score."""
        det1 = make_detection(xmin=0, ymin=0, xmax=100, ymax=50)
        det2 = make_detection(xmin=5, ymin=5, xmax=105, ymax=55)  # ~90% overlap
        det1 = det1.model_copy(update={"calibrated_confidence": 0.95})
        det2 = det2.model_copy(update={"calibrated_confidence": 0.50})
        result = self.reducer.filter([det1, det2], SensorType.SAR)
        # With soft-NMS: det2 may be kept but decayed or dropped if below minimal score
        # Both should not have exactly their original scores
        scores = sorted([d.calibrated_confidence for d in result], reverse=True)
        if len(result) == 2:
            assert scores[1] < 0.50, "Overlapping box should have decayed score"

    def test_empty_input(self):
        assert self.reducer.filter([], SensorType.SAR) == []

    def test_fp_flags_populated_on_reject(self):
        """Rejected by SAR area filter — checks no crash (filter removes item, no flag on kept)."""
        det = make_detection(xmin=0, ymin=0, xmax=2, ymax=2, sensor_type=SensorType.SAR)
        # area = 4 < 16 → should be rejected
        result = self.reducer.filter([det], SensorType.SAR)
        assert len(result) == 0


# ===========================================================================
# SituationScorer tests
# ===========================================================================
class TestSituationScorer:
    def setup_method(self):
        from inference.scoring.situation import SituationScorer

        self.scorer = SituationScorer()

    def test_sar_no_time_penalty(self):
        """SAR should never get a time-of-day penalty."""
        det_night = make_detection(
            detection_datetime="2024-01-10T02:00:00Z", sensor_type=SensorType.SAR
        )
        score = self.scorer.score(det_night, SensorType.SAR)
        # Should be neutral or positive, never large negative
        assert score >= -0.05, "SAR should not have large time penalty"

    def test_eo_nighttime_penalty(self):
        """EO at 2:00 UTC should get a strong negative adjustment."""
        det = make_detection(
            detection_datetime="2024-01-10T02:00:00Z", sensor_type=SensorType.EO
        )
        score = self.scorer.score(det, SensorType.EO)
        assert score < 0, "Nighttime EO detection should have negative situation score"

    def test_eo_daytime_positive(self):
        """EO at 12:00 UTC (midday) should have positive adjustment."""
        det = make_detection(
            detection_datetime="2024-01-10T12:00:00Z", sensor_type=SensorType.EO
        )
        score = self.scorer.score(det, SensorType.EO)
        assert score >= 0, "Daytime EO should have non-negative situation score"

    def test_shipping_lane_latitude(self):
        """Detection at lat=40.0 (N. Atlantic shipping) should get positive zone score."""
        det = make_detection(lat=40.0, lon=-50.0, sensor_type=SensorType.SAR)
        score = self.scorer.score(det, SensorType.SAR)
        assert score >= 0, "Main shipping lane latitude should be positive"

    def test_polar_region_penalty(self):
        """Detection at very high latitude > 70° should get slight penalty."""
        det = make_detection(lat=75.0, lon=-20.0, sensor_type=SensorType.SAR)
        score = self.scorer.score(det, SensorType.SAR)
        # Zone factor alone: -0.05. Other components may add more.
        assert score <= 0, "Polar region should not be boosted"

    def test_score_bounded(self):
        """Any situation score must be in [-0.3, +0.3]."""
        test_cases = [
            make_detection(
                lat=80.0,
                detection_datetime="2024-01-10T02:00:00Z",
                sensor_type=SensorType.EO,
            ),
            make_detection(
                lat=35.0,
                detection_datetime="2024-06-15T14:00:00Z",
                sensor_type=SensorType.SAR,
            ),
            make_detection(
                lat=0.0,
                lon=0.0,
                detection_datetime="2024-01-10T04:00:00Z",
                sensor_type=SensorType.EO,
            ),
        ]
        for det in test_cases:
            score = self.scorer.score(det, det.sensor_type)
            assert -0.30 <= score <= 0.30, f"Score {score} out of bounds for {det}"

    def test_compute_final_score_clamps(self):
        """final_score should always be in [0.01, 1.0]."""
        from inference.scoring.situation import SituationScorer

        s = SituationScorer()
        assert s.compute_final_score(2.0, 0.5) == 1.0  # clamped to 1.0
        assert s.compute_final_score(-0.5, 0.0) == 0.01  # clamped to 0.01
        assert abs(s.compute_final_score(0.6, 0.1) - 0.7) < 1e-9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
