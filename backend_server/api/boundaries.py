"""
API endpoint to serve maritime boundaries as GeoJSON.
Reads directly from cached files on disk (no DB dependency).
Combines EEZ boundaries and shipping lanes into a single response.
"""

import json
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from shared.config import MASK_DIR

router = APIRouter(prefix="/api/v1/boundaries", tags=["boundaries"])

from ..services.boundaries import EEZ_FILE, SHIPPING_LANES_FILE


def _load_eez_features() -> list:
    """Load EEZ features with normalized properties."""
    if not os.path.exists(EEZ_FILE):
        return []
    try:
        with open(EEZ_FILE, "r") as f:
            data = json.load(f)
        features = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            features.append({
                "type": "Feature",
                "properties": {
                    "name": f"{props.get('Country', 'Unknown')} EEZ",
                    "type": "eez",
                    "country": props.get("ISO_A3", ""),
                },
                "geometry": feature.get("geometry"),
            })
        return features
    except Exception as e:
        print(f"[Boundaries API] Error reading EEZ file: {e}")
        return []


def _load_shipping_lane_features() -> list:
    """Load shipping lane features with normalized properties."""
    if not os.path.exists(SHIPPING_LANES_FILE):
        return []
    try:
        with open(SHIPPING_LANES_FILE, "r") as f:
            data = json.load(f)
        features = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            lane_type = props.get("Type", "Major")
            features.append({
                "type": "Feature",
                "properties": {
                    "name": f"{lane_type} Shipping Lane",
                    "type": "shipping_lane",
                    "lane_class": lane_type,
                },
                "geometry": feature.get("geometry"),
            })
        return features
    except Exception as e:
        print(f"[Boundaries API] Error reading shipping lanes file: {e}")
        return []


@router.get("")
async def get_boundaries():
    """
    Returns all boundary data as a single GeoJSON FeatureCollection.
    Combines EEZ boundaries and shipping lanes.
    """
    features = []
    features.extend(_load_eez_features())
    features.extend(_load_shipping_lane_features())

    return {
        "type": "FeatureCollection", 
        "features": features
    }
