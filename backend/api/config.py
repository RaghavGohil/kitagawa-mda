"""
Classification Config API — returns authoritative classification states and their UI properties.
The frontend uses this to drive all colors and labels dynamically.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("/classification")
async def get_classification_config():
    """
    Return the authoritative vessel classification states with colors and labels.
    Frontend fetches this once on startup and uses it for all rendering decisions.
    """
    return {
        "states": {
            "identified": {
                "color": "#3b82f6",
                "label": "Identified",
                "description": "AIS-correlated within 500m tolerance",
            },
            "unidentified": {
                "color": "#ef4444",
                "label": "Unidentified",
                "description": "No matching AIS data at time of detection (potential dark vessel)",
            },
        }
    }
