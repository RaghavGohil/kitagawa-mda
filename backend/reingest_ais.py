import asyncio
import os
from sqlalchemy import text
from backend.db.connection import get_db
from backend.services.ingestion import _insert_ais_csv

async def do():
    async for db in get_db():
        csv_path = "/data/AIS/ais-2025-01-02.csv"
        if os.path.exists(csv_path):
            print(f"Re-ingesting {csv_path} to populate ais_vessels")
            await _insert_ais_csv(csv_path, db, 50000)
            
            # Check ais_vessels
            res = await db.execute(text("SELECT COUNT(*) FROM ais_vessels"))
            print("Total AIS vessels:", res.scalar())
        else:
            print(f"{csv_path} not found")

if __name__ == "__main__":
    asyncio.run(do())
