import asyncio
import time
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from datetime import datetime, timezone

DATABASE_URL = "postgresql+asyncpg://kitagawa:kitagawa@localhost:5432/kitagawa"


async def run_test():
    engine = create_async_engine(DATABASE_URL)

    # Parameters from the user's log
    params = {
        "min_lon": 17.665329,
        "min_lat": -34.273673,
        "max_lon": 18.983688,
        "max_lat": -33.774581,
        "buffer": 0.6591795,
        "center_time": datetime(2026, 3, 24, 2, 0, tzinfo=timezone.utc),
        "focal_start": datetime(2026, 3, 24, 2, 0, tzinfo=timezone.utc),  # simplified
        "focal_end": datetime(2026, 3, 24, 6, 0, tzinfo=timezone.utc),  # simplified
        "limit": 1000,
        "tolerance": 0.0001,
        "mmsis_arr": [538011716, 352071000, 566513000],  # dummy subset
    }

    spatial_filter = "ST_Expand(ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326), :buffer)"
    focal_time_filter = "AND timestamp >= :focal_start AND timestamp <= :focal_end"

    # 1. OLD QUERY (Simplified mockup of what caused the timeout)
    old_lateral = f"""
        (
            SELECT timestamp, geom, sog, cog
            FROM ais_tracks
            WHERE mmsi = m.mmsi
              AND geom && {spatial_filter}
              {focal_time_filter}
            ORDER BY timestamp DESC
            LIMIT 500
        )
    """

    # 2. NEW OPTIMIZED QUERY
    new_lateral = f"""
        (
            SELECT * FROM (
                (SELECT timestamp, geom, sog, cog
                FROM ais_tracks
                WHERE mmsi = m.mmsi
                  AND timestamp <= :center_time
                  AND geom && {spatial_filter}
                ORDER BY timestamp DESC
                LIMIT 10)
                UNION ALL
                (SELECT timestamp, geom, sog, cog
                FROM ais_tracks
                WHERE mmsi = m.mmsi
                  AND timestamp > :center_time
                  AND geom && {spatial_filter}
                ORDER BY timestamp ASC
                LIMIT 10)
            ) sub
            ORDER BY timestamp DESC
        )
    """

    async def benchmark(label, lateral_sql):
        sql = text(f"""
            WITH target_mmsis AS (
                SELECT DISTINCT mmsi FROM ais_tracks 
                WHERE geom && {spatial_filter} {focal_time_filter}
                LIMIT :limit
            )
            SELECT m.mmsi, jsonb_agg(jsonb_build_object('t', t.timestamp))
            FROM target_mmsis m
            CROSS JOIN LATERAL {lateral_sql} t
            GROUP BY m.mmsi
        """)

        start = time.time()
        async with engine.connect() as conn:
            try:
                res = await conn.execute(sql, params)
                rows = res.fetchall()
                duration = time.time() - start
                print(f"{label}: {duration:.4f}s - {len(rows)} vessels found")
            except Exception as e:
                print(f"{label} FAILED: {e}")

    print("Running benchmarks...")
    await benchmark("BASELINE (Window scan)", old_lateral)
    await benchmark("OPTIMIZED (Nearest neighbor)", new_lateral)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_test())
