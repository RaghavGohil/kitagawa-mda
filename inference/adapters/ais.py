"""
AIS Data Adapter interface.

Provides an abstract base class for plugging in different AIS data sources:
  - NOAAAISAdapter: historical daily CSVs from NOAA
  - LiveAISAdapter: real-time websocket via AISStream.io

Both expose a unified interface: get_tracks() and get_density().
This allows the SituationScorer and correlation service to query AIS data
without caring about the underlying source.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from shared.schemas import AISTrackPoint


class AISDataAdapter(ABC):
    """
    Abstract base class for AIS data sources.

    Subclasses encapsulate where and how AIS data is fetched,
    keeping correlation and scoring code agnostic of the source.
    """

    @abstractmethod
    def get_tracks(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        time_start: datetime,
        time_end: datetime,
    ) -> list[AISTrackPoint]:
        """
        Retrieve AIS position reports within a bounding box and time window.

        Args:
            lat_min, lon_min, lat_max, lon_max: Geographic bounding box.
            time_start, time_end: UTC datetime range.

        Returns:
            List of AISTrackPoint objects sorted by timestamp.
        """
        ...

    @abstractmethod
    def get_density(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        time_start: datetime,
        time_end: datetime,
    ) -> float:
        """
        Estimate ship traffic density in ships per 100 km² for the given
        bounding box and time window.

        Used by SituationScorer to adjust detection confidence in high-traffic areas.

        Returns:
            Float >= 0.0. Typical range 0.0 (open ocean) to 50+ (port approach).
        """
        ...


class NOAAAISAdapter(AISDataAdapter):
    """
    AIS data adapter that reads from locally ingested NOAA historical CSVs
    via the PostGIS database (ais_tracks table).

    This is a thin wrapper around the existing DB import pipeline.
    """

    def __init__(self, db_session_factory):
        """
        Args:
            db_session_factory: Callable returning an AsyncSession context manager.
                                Typically `async_session` from db/connection.py.
        """
        self._session_factory = db_session_factory

    def get_tracks(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        time_start: datetime,
        time_end: datetime,
    ) -> list[AISTrackPoint]:
        """
        Synchronous wrapper — use run_async_get_tracks() for async contexts.
        For now, returns empty list (designed for async usage via DB).
        """
        # Async version must be called from correlation/scoring services
        return []

    async def run_async_get_tracks(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        time_start: datetime,
        time_end: datetime,
    ) -> list[AISTrackPoint]:
        """
        Async: query ais_tracks table within bounding box and time range.
        Returns list of AISTrackPoint objects.
        """
        from sqlalchemy import text

        async with self._session_factory() as db:
            result = await db.execute(
                text("""
                    SELECT mmsi, timestamp,
                           ST_Y(geom) AS lat, ST_X(geom) AS lon,
                           COALESCE(sog, 0) AS sog, COALESCE(cog, 0) AS cog
                    FROM ais_tracks
                    WHERE timestamp BETWEEN :tstart AND :tend
                      AND geom && ST_MakeEnvelope(:lon_min, :lat_min, :lon_max, :lat_max, 4326)
                    ORDER BY mmsi, timestamp
                """),
                {
                    "tstart": time_start,
                    "tend": time_end,
                    "lat_min": lat_min,
                    "lat_max": lat_max,
                    "lon_min": lon_min,
                    "lon_max": lon_max,
                },
            )
            rows = result.fetchall()

        return [
            AISTrackPoint(
                mmsi=int(r[0]),
                timestamp=r[1],
                latitude=float(r[2]),
                longitude=float(r[3]),
                sog=float(r[4]),
                cog=float(r[5]),
            )
            for r in rows
        ]

    def get_density(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        time_start: datetime,
        time_end: datetime,
    ) -> float:
        """Returns 0.0 — use run_async_get_density() from async contexts."""
        return 0.0

    async def run_async_get_density(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        time_start: datetime,
        time_end: datetime,
    ) -> float:
        """
        Count distinct MMSIs in bounding box and time window,
        normalize by area to get ships / 100 km².
        """
        from sqlalchemy import text
        import math

        async with self._session_factory() as db:
            result = await db.execute(
                text("""
                    SELECT COUNT(DISTINCT mmsi) AS ship_count
                    FROM ais_tracks
                    WHERE timestamp BETWEEN :tstart AND :tend
                      AND geom && ST_MakeEnvelope(:lon_min, :lat_min, :lon_max, :lat_max, 4326)
                """),
                {
                    "tstart": time_start,
                    "tend": time_end,
                    "lat_min": lat_min,
                    "lat_max": lat_max,
                    "lon_min": lon_min,
                    "lon_max": lon_max,
                },
            )
            row = result.fetchone()
            count = int(row[0]) if row else 0

        # Estimate bounding box area in km²
        # 1° lat ≈ 111 km, 1° lon ≈ 111 * cos(lat_mid) km
        lat_mid = (lat_min + lat_max) / 2.0
        height_km = (lat_max - lat_min) * 111.0
        width_km = (lon_max - lon_min) * 111.0 * abs(math.cos(math.radians(lat_mid)))
        area_km2 = max(height_km * width_km, 1.0)

        # Ships per 100 km²
        return round((count / area_km2) * 100.0, 2)


class LiveAISAdapter(AISDataAdapter):
    """
    AIS data adapter wrapping the real-time AISStream.io WebSocket ingestion.

    Delegates to the live AIS service's in-memory buffer for recent positions.
    Falls back gracefully if the live service is not running.
    """

    def get_tracks(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        time_start: datetime,
        time_end: datetime,
    ) -> list[AISTrackPoint]:
        """
        Query live AIS positions from the in-memory buffer.
        Returns positions within 30 minutes of query time.
        """
        try:
            from backend.services.ais_stream import get_live_positions

            positions = get_live_positions(lat_min, lon_min, lat_max, lon_max)
            return [
                AISTrackPoint(
                    mmsi=p["mmsi"],
                    timestamp=p["timestamp"],
                    latitude=p["lat"],
                    longitude=p["lon"],
                    sog=p.get("sog"),
                    cog=p.get("cog"),
                )
                for p in positions
            ]
        except Exception:
            return []

    def get_density(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        time_start: datetime,
        time_end: datetime,
    ) -> float:
        """Estimate density from live buffer."""
        tracks = self.get_tracks(
            lat_min, lon_min, lat_max, lon_max, time_start, time_end
        )
        import math

        lat_mid = (lat_min + lat_max) / 2.0
        height_km = (lat_max - lat_min) * 111.0
        width_km = (lon_max - lon_min) * 111.0 * abs(math.cos(math.radians(lat_mid)))
        area_km2 = max(height_km * width_km, 1.0)
        unique_mmsi = len({t.mmsi for t in tracks})
        return round((unique_mmsi / area_km2) * 100.0, 2)
