import asyncio
import httpx
import time

BASE_URL = "http://localhost:8000/api/v1"


async def fetch_tracks(client):
    try:
        # Request a large area to trigger substantial DB work
        resp = await client.get(
            f"{BASE_URL}/ais/tracks",
            params={
                "min_lon": -180,
                "min_lat": -90,
                "max_lon": 180,
                "max_lat": 90,
                "zoom": 6,
                "limit": 1000,
            },
            timeout=30.0,
        )
        return resp.status_code
    except Exception as e:
        return str(e)


async def fetch_vessels(client):
    try:
        resp = await client.get(
            f"{BASE_URL}/vessels", params={"zoom": 15, "limit": 100}, timeout=30.0
        )
        return resp.status_code
    except Exception as e:
        return str(e)


async def main():
    print("Starting load test...")
    async with httpx.AsyncClient() as client:
        # Fire 10 concurrent requests (5 tracks + 5 vessels)
        tasks = []
        for _ in range(5):
            tasks.append(fetch_tracks(client))
            tasks.append(fetch_vessels(client))

        start_time = time.time()
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        success_count = sum(1 for r in results if r == 200)
        error_count = len(results) - success_count

        print(f"Finished in {end_time - start_time:.2f} seconds")
        print(f"Successes: {success_count}")
        print(f"Errors: {error_count}")

        if error_count > 0:
            print("First few errors:")
            for r in [res for res in results if res != 200][:5]:
                print(f" - {r}")


if __name__ == "__main__":
    asyncio.run(main())
