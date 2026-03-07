import asyncio
import os
import sys

sys.path.append("/home/TheLowEnd/Documents/projects/kitagawa-backend")

from backend_server.db.connection import async_session
from sqlalchemy import text

async def main():
    try:
        async with async_session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM detections"))
            count = result.scalar()
            print(f"Total detections in DB: {count}")
            
            result = await session.execute(text("SELECT * FROM processed_images"))
            images = result.all()
            print(f"Processed images: {len(images)} - {images}")
            
            # check latest pipeline status if any
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
