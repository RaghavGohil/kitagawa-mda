
import os
import asyncio
from sqlalchemy import text
os.environ["POSTGRES_HOST"] = "localhost"
from backend_server.db.connection import get_db

async def check():
    async for db in get_db():
        res = await db.execute(text("SELECT ST_Y(geom), ST_X(geom), detection_datetime FROM detections WHERE detection_datetime >= '2025-01-02' AND detection_datetime < '2025-01-03' LIMIT 20"))
        rows = res.fetchall()
        for r in rows:
            print(f"Lat: {r[0]}, Lon: {r[1]}, Time: {r[2]}")

if __name__ == "__main__":
    asyncio.run(check())
