import asyncio
import httpx
import time
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api/v1"


async def test_performance():
    async with httpx.AsyncClient() as client:
        now = datetime.now()
        start_iso = (now - timedelta(days=2)).isoformat()
        end_iso = now.isoformat()
        center_iso = (now - timedelta(days=1)).isoformat()

        # 1. Wide query without center_time (baseline)
        start_time = time.time()
        resp_wide = await client.get(
            f"{BASE_URL}/ais/tracks",
            params={
                "min_lon": -5,
                "min_lat": 45,
                "max_lon": -4,
                "max_lat": 46,
                "zoom": 10,
                "limit": 200,
                "time_start": start_iso,
                "time_end": end_iso,
            },
            timeout=30.0,
        )
        wide_duration = time.time() - start_time

        # 2. Narrow query WITH center_time (focal window optimization)
        start_time = time.time()
        resp_focal = await client.get(
            f"{BASE_URL}/ais/tracks",
            params={
                "min_lon": -5,
                "min_lat": 45,
                "max_lon": -4,
                "max_lat": 46,
                "zoom": 10,
                "limit": 200,
                "time_start": start_iso,
                "time_end": end_iso,
                "center_time": center_iso,
                "window_mins": 120,
            },
            timeout=30.0,
        )
        focal_duration = time.time() - start_time

        print(f"Baseline (Global window) duration: {wide_duration:.4f}s")
        print(f"Optimized (Focal window) duration: {focal_duration:.4f}s")

        if resp_focal.status_code == 200:
            data = resp_focal.json()
            print(f"Tracks found: {len(data.get('tracks', []))}")
            if data.get("tracks"):
                print(f"Points in first track: {len(data['tracks'][0]['points'])}")
        else:
            print(
                f"Optimized query failed with status {resp_focal.status_code}: {resp_focal.text}"
            )


if __name__ == "__main__":
    asyncio.run(test_performance())
