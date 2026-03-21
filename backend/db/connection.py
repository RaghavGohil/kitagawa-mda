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
    Initialize the database using Alembic migrations.

    Runs 'alembic upgrade head' programmatically so that schema changes
    are applied incrementally instead of relying on create_all (which
    can't alter existing tables).
    """
    from backend.db.models import (
        Detection,
        AISTrack,
        ImageChip,
        AISVessel,
        ProcessedImage,
        AISCoverageDate,
        MaritimeBoundary,
    )

    # Step 1: Ensure PostGIS extension exists (must happen before migrations)
    async with engine.begin() as conn:
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS postgis")
        )

    # Step 2: Run Alembic migrations (or fall back to create_all)
    import os
    import glob

    alembic_ini = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    versions_dir = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")

    # Check if there are any actual migration files (not just .gitkeep)
    has_migrations = bool(glob.glob(os.path.join(versions_dir, "*.py")))

    if os.path.exists(alembic_ini) and has_migrations:
        from alembic.config import Config
        from alembic import command

        alembic_cfg = Config(alembic_ini)
        alembic_cfg.set_main_option(
            "script_location",
            os.path.join(os.path.dirname(__file__), "..", "alembic"),
        )
        command.upgrade(alembic_cfg, "head")
        print("[DB] Alembic migrations applied successfully.")
    else:
        # No migrations yet — create tables directly, then stamp so Alembic
        # knows the current state when the first migration is generated.
        print("[DB] No Alembic migrations found, using create_all (first-time setup).")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Stamp with head so future autogenerate diffs correctly
        if os.path.exists(alembic_ini):
            try:
                from alembic.config import Config
                from alembic import command

                alembic_cfg = Config(alembic_ini)
                alembic_cfg.set_main_option(
                    "script_location",
                    os.path.join(os.path.dirname(__file__), "..", "alembic"),
                )
                command.stamp(alembic_cfg, "head")
                print("[DB] Stamped Alembic version to 'head'.")
            except Exception as e:
                print(f"[DB] Could not stamp Alembic (non-critical): {e}")


async def close_db():
    """Dispose of the connection pool."""
    await engine.dispose()
