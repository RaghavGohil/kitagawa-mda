
import os
import asyncio
from sqlalchemy import text
os.environ["POSTGRES_HOST"] = "localhost"
from backend_server.db.connection import get_db

async def check():
    async for db in get_db():
        # Check detections
        res = await db.execute(text("SELECT COUNT(*), MIN(detection_datetime), MAX(detection_datetime) FROM detections"))
        det_count, det_min, det_max = res.fetchone()
        print(f"Detections: {det_count} total, range: {det_min} to {det_max}")

        # Check AIS tracks
        res = await db.execute(text("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM ais_tracks"))
        ais_count, ais_min, ais_max = res.fetchone()
        print(f"AIS tracks: {ais_count} total, range: {ais_min} to {ais_max}")

        # Check correlations
        res = await db.execute(text("SELECT COUNT(*) FROM detections WHERE mmsi IS NOT NULL"))
        corr_count = res.scalar()
        print(f"Correlations: {corr_count}")

        # Check unique MMSIs in tracks
        res = await db.execute(text("SELECT COUNT(DISTINCT mmsi) FROM ais_tracks"))
        mmsi_count = res.scalar()
        print(f"Unique MMSIs in AIS: {mmsi_count}")

        # Check image chips
        res = await db.execute(text("SELECT COUNT(*) FROM image_chips"))
        chips_count = res.scalar()
        print(f"Image chips: {chips_count}")

        # Check EO detections
        res = await db.execute(text("SELECT COUNT(*) FROM detections WHERE sensor_type = 'EO'"))
        eo_count = res.scalar()
        print(f"EO detections: {eo_count}")

if __name__ == "__main__":
    asyncio.run(check())
