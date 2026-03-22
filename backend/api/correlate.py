from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.connection import get_db
from backend.services.correlation import correlate_single_detection
from backend.api.vessels import get_vessel

router = APIRouter(prefix="/api/v1/correlate", tags=["correlation"])


@router.post("/{detection_id}")
async def manual_correlate(detection_id: int, db: AsyncSession = Depends(get_db)):
    """
    Trigger an on-the-fly correlation for a single detection.
    Useful for 'Live Identification' in the UI.
    """
    await correlate_single_detection(db, detection_id)

    # Return the updated vessel data (standard vessel detail response)
    # If identified, mmsi will be the real MMSI. If not, it stays as -detection_id
    res = await db.execute(
        text("SELECT mmsi FROM detections WHERE id = :id"), {"id": detection_id}
    )
    row = res.fetchone()
    mmsi = row[0] if row and row[0] else -detection_id

    return await get_vessel(mmsi, db)
