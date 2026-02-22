
import os
import asyncio
from sqlalchemy import text
os.environ["POSTGRES_HOST"] = "localhost"
from backend_server.db.connection import get_db

async def check():
    async for db in get_db():
        res = await db.execute(text("SELECT COUNT(*) FROM ais_tracks WHERE ST_Intersects(geom, ST_MakeEnvelope(-120, 32, -117, 35, 4326))"))
        print(f"AIS tracks in AOI: {res.scalar()}")

if __name__ == "__main__":
    asyncio.run(check())
