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
                "color": "#10b981",
                "label": "Identified",
                "description": "AIS-correlated within 500m tolerance",
            },
            "anomaly": {
                "color": "#ef4444",
                "label": "Dark Vessel",
                "description": "Detected in coverage area with no AIS transmission",
            },
            "out_of_coverage": {
                "color": "#6b7280",
                "label": "Out of Coverage",
                "description": "Detected but no AIS data available for this area and date",
            },
        }
    }
