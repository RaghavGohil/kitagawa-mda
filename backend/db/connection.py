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
    """
    Initialize the database.

    1. Ensures PostGIS extension exists.
    2. Creates all base tables via SQLAlchemy (safe IF NOT EXISTS).
    3. Runs Alembic migrations for any incremental schema changes.
    """
    # Import all models here so they are registered with Base.metadata
    # for the create_all call below.
    from backend.db.models import (
        Detection,
        AISTrack,
        ImageChip,
        AISVessel,
        ProcessedImage,
        AISCoverageDate,
        MaritimeBoundary,
    )

    # Step 1: Ensure PostGIS extension exists
    async with engine.begin() as conn:
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS postgis")
        )

    # Step 2: Ensure all base tables exist (SQLAlchemy create_all is safe on existing tables)
    print("[DB] Ensuring base tables exist...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Step 3: Run Alembic migrations for incremental changes
    import os

    alembic_ini = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")

    if os.path.exists(alembic_ini):
        print("[DB] Running Alembic migrations...")
        try:
            from alembic.config import Config
            from alembic import command

            alembic_cfg = Config(alembic_ini)
            alembic_cfg.set_main_option(
                "script_location",
                os.path.join(os.path.dirname(__file__), "..", "alembic"),
            )
            # Run migrations (matches head)
            command.upgrade(alembic_cfg, "head")
            print("[DB] Alembic migrations applied/verified.")
        except Exception as e:
            # We don't fail here if it's just a 'version already at head' etc.
            print(f"[DB] Alembic migration notice: {e}")
    else:
        print("[DB] No alembic.ini found, skipping incremental migrations.")


async def close_db():
    """Dispose of the connection pool."""
    await engine.dispose()
