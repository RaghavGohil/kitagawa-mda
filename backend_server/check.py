import asyncio
import os
from sqlalchemy import text
from backend_server.db.connection import get_db

async def check():
    async for db in get_db():
        print("=== DETECTIONS ===")
        res = await db.execute(text("SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, detection_datetime, mmsi, custom_name FROM detections LIMIT 10"))
        for r in res.fetchall():
            print(r)
            
        print("\n=== AIS TRACKS ===")
        res = await db.execute(text("SELECT COUNT(*) FROM ais_tracks"))
        print("Total AIS tracks:", res.scalar())
        
        res = await db.execute(text("SELECT mmsi, ST_X(geom) as lon, ST_Y(geom) as lat, timestamp FROM ais_tracks LIMIT 10"))
        for r in res.fetchall():
            print(r)

if __name__ == "__main__":
    asyncio.run(check())
