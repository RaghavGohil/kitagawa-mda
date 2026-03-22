import asyncio
from sqlalchemy import text
from backend.db.connection import async_session


async def main():
    async with async_session() as db:
        # Check active connections
        res = await db.execute(
            text("SELECT count(*) FROM pg_stat_activity WHERE datname = 'kitagawa'")
        )
        conn_count = res.scalar()
        print(f"Active connections: {conn_count}")

        # Check wait events (for locking issues)
        res = await db.execute(
            text(
                "SELECT wait_event_type, wait_event, count(*) FROM pg_stat_activity WHERE wait_event IS NOT NULL GROUP BY 1, 2"
            )
        )
        waits = res.fetchall()
        if waits:
            print("Wait events:")
            for w in waits:
                print(f"  {w[0]}/{w[1]}: {w[2]}")
        else:
            print("No significant wait events.")

        # Check indices on ais_tracks
        res = await db.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'ais_tracks'"
            )
        )
        indices = res.fetchall()
        print("Indices on ais_tracks:")
        for idx in indices:
            print(f"  {idx[0]}: {idx[1]}")

        res = await db.execute(text("SELECT count(*) FROM detections"))
        detections_count = res.scalar()
        print(f"Total detections: {detections_count}")


if __name__ == "__main__":
    asyncio.run(main())
