"""
Scoring package for post-inference quality estimation.

Provides:
  - ConfidenceCalibrator: dataset-free temperature scaling + adaptive thresholding
  - FPFNReducer: geometric sanity checks + soft-NMS
  - SituationScorer: context-aware score adjustments
"""

from inference.scoring.confidence import ConfidenceCalibrator
from inference.scoring.fp_fn import FPFNReducer
from inference.scoring.situation import SituationScorer

__all__ = ["ConfidenceCalibrator", "FPFNReducer", "SituationScorer"]
