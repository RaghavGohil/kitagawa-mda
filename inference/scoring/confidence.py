"""
Dataset-free confidence calibration for YOLO vessel detections.

Uses temperature scaling (no labels required):
  1. Convert raw YOLO confidence to logit space: logit = log(p / (1 - p))
  2. Divide by sensor-specific temperature T to soften overconfidence
  3. Convert back via sigmoid: calibrated = 1 / (1 + exp(-logit/T))
  4. Normalize batch so max calibrated score = 1.0

Adaptive thresholding:
  Uses 1D Otsu's method on the calibrated score histogram so the cutoff
  is data-driven per image, not a fixed constant.
"""

from __future__ import annotations

import numpy as np

from shared.schemas import SensorType
from inference.scoring.calibration_params import get_temperature


class ConfidenceCalibrator:
    """
    Dataset-free confidence calibration via temperature scaling.

    No labeled ground-truth data required.
    Temperature parameters can be overridden via environment variables.
    """

    # Epsilon to avoid log(0) in logit computation
    _EPS = 1e-6

    def calibrate_batch(
        self,
        raw_scores: list[float],
        sensor_type: SensorType,
    ) -> list[float]:
        """
        Calibrate a batch of raw YOLO confidence scores for a single image.

        Steps:
          1. Temperature scaling (softens per-sensor overconfidence)
          2. Batch max-normalization (makes relative quality within image clear)

        Args:
            raw_scores: List of raw YOLO confidence values in [0, 1].
            sensor_type: SAR or EO — determines temperature.

        Returns:
            List of calibrated confidences in [0, 1], same order as input.
        """
        if not raw_scores:
            return []

        scores = np.array(raw_scores, dtype=np.float64)
        # Clip to avoid degenerate logit
        scores = np.clip(scores, self._EPS, 1.0 - self._EPS)

        T = get_temperature(sensor_type)

        # Logit transform
        logits = np.log(scores / (1.0 - scores))

        # Temperature scaling then sigmoid
        calibrated = 1.0 / (1.0 + np.exp(-logits / T))

        # Per-image max normalization so relative quality is preserved
        batch_max = float(np.max(calibrated))
        if batch_max > self._EPS:
            calibrated = calibrated / batch_max

        return calibrated.tolist()

    def calibrate_single(
        self,
        raw_score: float,
        sensor_type: SensorType,
    ) -> float:
        """
        Calibrate a single score. For use when batch context is unavailable.
        Note: max-normalization is not applied here since there's no batch.
        """
        score = float(np.clip(raw_score, self._EPS, 1.0 - self._EPS))
        T = get_temperature(sensor_type)
        logit = np.log(score / (1.0 - score))
        return float(1.0 / (1.0 + np.exp(-logit / T)))

    @staticmethod
    def adaptive_threshold(calibrated_scores: list[float]) -> float:
        """
        Compute a data-driven confidence threshold using 1D Otsu's method.

        The threshold separates the low-confidence (noise/FP) cluster from the
        high-confidence (likely vessel) cluster without any hard-coded value.

        Args:
            calibrated_scores: List of calibrated confidence values in [0, 1].

        Returns:
            Threshold value in [0, 1]. Detections below this should be
            considered low quality. Returns 0.0 if too few detections exist
            to compute a meaningful threshold.
        """
        if len(calibrated_scores) < 3:
            # Too few detections to find a meaningful valley — keep all
            return 0.0

        scores = np.array(calibrated_scores, dtype=np.float64)

        # Compute 1D Otsu threshold on score histogram
        n_bins = max(10, min(50, len(scores)))
        hist, bin_edges = np.histogram(scores, bins=n_bins, range=(0.0, 1.0))
        bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
        hist = hist.astype(np.float64)
        total = hist.sum()

        if total == 0:
            return 0.0

        # Otsu: maximize inter-class variance
        best_thresh = 0.0
        best_var = -1.0

        w_low = 0.0
        sum_low = 0.0

        total_mean = np.sum(bin_centers * hist) / total

        for i in range(len(hist) - 1):
            w_low += hist[i]
            w_high = total - w_low
            if w_low == 0 or w_high == 0:
                continue

            sum_low += bin_centers[i] * hist[i]
            mean_low = sum_low / w_low
            mean_high = (total_mean * total - sum_low) / w_high

            inter_var = (w_low * w_high / total**2) * (mean_low - mean_high) ** 2
            if inter_var > best_var:
                best_var = inter_var
                best_thresh = bin_edges[i + 1]

        # Safety guard: don't produce a threshold above 0.8 or below 0.1
        # (prevents degenerate cases where Otsu finds a poor split)
        return float(np.clip(best_thresh, 0.05, 0.80))
