"""
Async SQLAlchemy + GeoAlchemy2 database connection.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from shared.config import DATABASE_URL


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async DB session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables if they don't exist."""
    from backend_server.db.models import (  # noqa: F401 — ensure models are imported
        AISTrack,
        Detection,
        ImageChip,
        ProcessedImage,
        AISVessel,
    )
    async with engine.begin() as conn:
        # Enable PostGIS extension
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS postgis")
        )
        await conn.run_sync(Base.metadata.create_all)

        # Ensure unique constraint on ais_tracks(mmsi, timestamp) for deduplication
        # This is needed because Base.metadata.create_all won't modify existing tables.
        await conn.execute(
            __import__("sqlalchemy").text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'uq_ais_mmsi_timestamp'
                    ) THEN
                        ALTER TABLE ais_tracks ADD CONSTRAINT uq_ais_mmsi_timestamp UNIQUE (mmsi, timestamp);
                    END IF;
                EXCEPTION
                    WHEN duplicate_table THEN
                        -- Ignore if already existing
                        NULL;
                    WHEN others THEN
                        -- If adding constraint fails (e.g. due to existing duplicates), 
                        -- we log but don't crash.
                        RAISE NOTICE 'Could not add unique constraint to ais_tracks: %', SQLERRM;
                END $$;
            """)
        )


async def close_db():
    """Dispose of the connection pool."""
    await engine.dispose()
