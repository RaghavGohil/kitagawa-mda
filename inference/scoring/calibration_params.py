"""
Temperature scaling parameters for per-sensor confidence calibration.

Temperature (T) controls how much YOLO's overconfident raw scores are softened:
  - T > 1: softer (less confident) — appropriate for noisy/cluttered imagery
  - T = 1: no change (identity)
  - T < 1: sharper (more confident)

These are dataset-free defaults derived from maritime detection literature.
Override via environment variables: SAR_TEMP and EO_TEMP.
"""

import os
from shared.schemas import SensorType

# Default temperatures per sensor type
_DEFAULT_TEMPS: dict[SensorType, float] = {
    SensorType.SAR: 1.5,  # SAR imagery has high ocean clutter → generous softening
    SensorType.EO: 1.3,  # EO has cloud/specular FPs → moderate softening
}

# Aspect ratio bounds [min, max] for FP/FN filtering by sensor
ASPECT_RATIO_BOUNDS: dict[SensorType, tuple[float, float]] = {
    SensorType.SAR: (
        0.08,
        12.0,
    ),  # SAR vessels can appear elongated/compressed from slant range
    SensorType.EO: (0.10, 10.0),
}

# Minimum pixel bounding-box area by sensor (sub-pixel blobs = noise)
MIN_PIXEL_AREA: dict[SensorType, float] = {
    SensorType.SAR: 16.0,  # SAR: smaller detection tiles (imgsz=128), so lower area threshold
    SensorType.EO: 64.0,  # EO: larger patch (512px), noise blobs are larger too
}

# Maximum plausible ship width in geographic km (used in plausibility filter)
MAX_SHIP_WIDTH_KM = 2.0

# Soft-NMS IoU decay sigma (higher = more aggressive decay)
SOFT_NMS_SIGMA: dict[SensorType, float] = {
    SensorType.SAR: 0.5,
    SensorType.EO: 0.5,
}

# Soft-NMS score threshold AFTER decay — only applied to drop decayed scores,
# NOT a fixed hard gate. Set to very low to avoid hard cutting.
SOFT_NMS_MINIMAL_SCORE = 0.05


def get_temperature(sensor_type: SensorType) -> float:
    """Return the calibration temperature for the given sensor type."""
    env_key = "SAR_TEMP" if sensor_type == SensorType.SAR else "EO_TEMP"
    env_val = os.getenv(env_key)
    if env_val is not None:
        try:
            return float(env_val)
        except ValueError:
            pass
    return _DEFAULT_TEMPS.get(sensor_type, 1.0)
