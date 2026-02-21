import asyncio
from backend_server.db.connection import get_db
from sqlalchemy import text

async def check_ais():
    async for db in get_db():
        result = await db.execute(text("SELECT count(*) FROM ais_tracks"))
        count = result.scalar()
        print(f"Total AIS records: {count}")
        
        if count > 0:
            result = await db.execute(text("SELECT ST_AsText(geom), timestamp FROM ais_tracks LIMIT 5"))
            for row in result.fetchall():
                print(row)
        break

if __name__ == "__main__":
    asyncio.run(check_ais())
