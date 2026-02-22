
import os
import asyncio
import pandas as pd
import numpy as np
from sqlalchemy import text
os.environ["POSTGRES_HOST"] = "localhost"
from backend_server.db.connection import get_db
from backend_server.services.correlation import run_correlation

async def test():
    async for db in get_db():
        # Check if there are any AIS tracks for Jan 2nd
        res = await db.execute(text("SELECT COUNT(*) FROM ais_tracks WHERE timestamp >= '2025-01-02' AND timestamp < '2025-01-03'"))
        print(f"AIS tracks for Jan 2nd: {res.scalar()}")

        # Check if there are any detections for Jan 2nd
        res = await db.execute(text("SELECT COUNT(*) FROM detections WHERE detection_datetime >= '2025-01-02' AND detection_datetime < '2025-01-03'"))
        print(f"Detections for Jan 2nd: {res.scalar()}")

        # Run correlation
        print("Running correlation...")
        correlated = await run_correlation(db)
        print(f"Correlated {correlated} detections.")

        # Check if any have MMSI now
        res = await db.execute(text("SELECT COUNT(*) FROM detections WHERE mmsi IS NOT NULL"))
        print(f"Detections with MMSI: {res.scalar()}")

if __name__ == "__main__":
    asyncio.run(test())
