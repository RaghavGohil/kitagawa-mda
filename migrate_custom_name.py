
import os
import asyncio
from sqlalchemy import text
os.environ["POSTGRES_HOST"] = "localhost"
from backend_server.db.connection import get_db

async def run():
    async for db in get_db():
        await db.execute(text('ALTER TABLE detections ADD COLUMN IF NOT EXISTS custom_name VARCHAR(512)'))
        await db.commit()
        print('Column added')

if __name__ == "__main__":
    asyncio.run(run())
