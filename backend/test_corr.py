import asyncio
from backend.db.connection import async_session
from backend.services.correlation import run_correlation

async def main():
    async with async_session() as db:
        print("Running correlation...")
        correlated = await run_correlation(db)
        print("Correlated:", correlated)

if __name__ == "__main__":
    asyncio.run(main())
