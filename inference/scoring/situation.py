"""
Situation-based scoring for vessel detections.

Computes a context-aware score adjustment in [-0.3, +0.3] based on:
  1. Maritime zone (open ocean vs. coastal vs. port) — no external DB needed,
     uses bounding box latitude as a simple proxy
  2. Time of day (EO sensors only see daylight; nighttime EO = suspicious)
  3. AIS traffic density hint (uses detection datetime to assess expected activity)
  4. Sensor-specific context (SAR is all-weather; EO is daylight-only)

The situation score is ADDITIVE to calibrated_confidence when computing
final_score:
  final_score = clip(calibrated_confidence + situation_score, 0, 1)
"""

from __future__ import annotations

from datetime import datetime

from shared.schemas import Detection, SensorType


class SituationScorer:
    """
    Context-aware score adjustment based on environmental and operational factors.

    All heuristics are label-free. They encode domain knowledge about
    where and when vessel detections are credible.
    """

    def score(self, detection: Detection, sensor_type: SensorType) -> float:
        """
        Compute a situation score adjustment for a single detection.

        Args:
            detection: The detection object (with geo coords and datetime).
            sensor_type: SAR or EO.

        Returns:
            Float in [-0.3, +0.3]. Positive = more credible given context.
            Negative = situation suggests increased FP likelihood.
        """
        adjustment = 0.0

        adjustment += self._zone_factor(detection)
        adjustment += self._time_of_day_factor(detection, sensor_type)
        adjustment += self._ais_density_hint(detection)
        adjustment += self._sensor_context(detection, sensor_type)

        # Clamp to maximum influence range
        return float(max(-0.30, min(0.30, adjustment)))

    # ------------------------------------------------------------------
    # 1. Zone factor
    # ------------------------------------------------------------------
    @staticmethod
    def _zone_factor(detection: Detection) -> float:
        """
        Simple latitude/longitude zone heuristic:
          - Deep ocean (far from any coast): vessels likely genuine → +0.05
          - Coastal band within ~50 km: neutral → 0.0
          - Very close to coastline (high FP zone from land reflections): -0.05

        Uses a simple latitude-band approximation since we don't always have the
        full maritime boundary DB available at inference time.
        """
        lat = abs(detection.vessel_latitude)

        # Crude open-ocean heuristic: far from continents
        # Main ship lanes: North Atlantic, Pacific
        # and lat between 10–60°
        if 10.0 <= lat <= 65.0:
            return +0.05  # Main shipping lanes — detection is plausible
        elif lat > 70.0:
            return -0.05  # Polar regions — unusual, slight FP risk from ice
        else:
            return 0.0

    # ------------------------------------------------------------------
    # 2. Time-of-day factor
    # ------------------------------------------------------------------
    @staticmethod
    def _time_of_day_factor(detection: Detection, sensor_type: SensorType) -> float:
        """
        EO sensors (optical) require sunlight. A valid EO detection at night is
        physically impossible — strong indicator of a false positive.
        SAR is all-weather, all-hours: no penalty.
        """
        if sensor_type == SensorType.SAR:
            return 0.0  # SAR works day and night

        # EO: check detection time
        if not detection.detection_datetime:
            return 0.0  # No timestamp — can't assess

        try:
            if isinstance(detection.detection_datetime, str):
                dt_str = detection.detection_datetime
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            else:
                dt = detection.detection_datetime

            hour_utc = dt.hour

            # Rough daylight window: 6:00–20:00 UTC (generous approximation).
            # Full rigor would use solar zenith angle, but this is label-free.
            if 6 <= hour_utc <= 20:
                return +0.05  # Daylight → EO detection is plausible
            else:
                return -0.15  # Nighttime EO detection is physically suspicious

        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # 3. AIS density hint
    # ------------------------------------------------------------------
    @staticmethod
    def _ais_density_hint(detection: Detection) -> float:
        """
        If AIS data suggests this area/time had active ship traffic,
        a detection is more likely genuine.

        This uses the detection_datetime to look at known busy shipping windows:
          - Peak hours (8:00–22:00 UTC) in main shipping regions → slight boost
          - Off-peak or unknown → neutral

        Full implementation can be upgraded to query AIS track density from DB.
        """
        if not detection.detection_datetime:
            return 0.0

        try:
            if isinstance(detection.detection_datetime, str):
                dt = datetime.fromisoformat(
                    detection.detection_datetime.replace("Z", "+00:00")
                )
            else:
                dt = detection.detection_datetime

            hour_utc = dt.hour
            # Shipping activity peaks during working hours (global average)
            if 8 <= hour_utc <= 22:
                return +0.05
            else:
                return 0.0

        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # 4. Sensor context
    # ------------------------------------------------------------------
    @staticmethod
    def _sensor_context(detection: Detection, sensor_type: SensorType) -> float:
        """
        Sensor-specific contextual adjustments:
          - SAR: IW GRDH mode over water is ideal for vessel detection → slight boost
          - EO: S2 MSI 10m bands are good but cloud contamination is an unknown risk
        """
        if sensor_type == SensorType.SAR:
            return +0.05  # SAR in IW mode specifically optimised for maritime
        else:
            return 0.0  # EO: neutral (cloudmask handles cloud FPs separately)

    # ------------------------------------------------------------------
    # Combined final score
    # ------------------------------------------------------------------
    @staticmethod
    def compute_final_score(
        calibrated_confidence: float,
        situation_score: float,
    ) -> float:
        """
        Fuse calibrated_confidence and situation_score into a single final_score.

        final_score = clip(calibrated_confidence + situation_score, 0.01, 1.0)
        """
        return float(max(0.01, min(1.0, calibrated_confidence + situation_score)))
