
import os
import asyncio
from sqlalchemy import text
os.environ["POSTGRES_HOST"] = "localhost"
from backend_server.db.connection import get_db

async def check():
    async for db in get_db():
        res = await db.execute(text("SELECT mmsi FROM ais_tracks LIMIT 20"))
        print(f"Sample MMSIs: {[r[0] for r in res.fetchall()]}")

if __name__ == "__main__":
    asyncio.run(check())
