"""
SQLAlchemy ORM models with PostGIS spatial columns.

Tables:
  - detections: vessel detections with Point geometry + spatial index
  - ais_tracks: AIS position reports with Point geometry + spatial index
  - image_chips: MinIO references for cropped detection images
"""

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    BigInteger,
    UniqueConstraint,
    func,
)

from backend_server.db.connection import Base


class Detection(Base):
    """
    A vessel detection from satellite imagery inference.

    Geometry: Point (vessel centroid lat/lon) + Polygon (bounding box).
    """
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_name = Column(String(512), nullable=False, index=True)
    sensor_type = Column(String(8), nullable=False, index=True)  # "SAR" or "EO"
    class_id = Column(Integer, default=0)
    confidence = Column(Float, nullable=False)

    # Bounding box coordinates
    bbox_xmin = Column(Float)
    bbox_ymin = Column(Float)
    bbox_xmax = Column(Float)
    bbox_ymax = Column(Float)

    detection_datetime = Column(DateTime(timezone=True), index=True)
    image_capture_start = Column(DateTime(timezone=True))
    image_capture_end = Column(DateTime(timezone=True))

    # PostGIS geometry columns
    geom = Column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )
    bbox_geom = Column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=True,
    )

    # AIS correlation result
    mmsi = Column(BigInteger, nullable=True, index=True)
    correlation_distance_m = Column(Float, nullable=True)
    custom_name = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_detection_sensor_datetime", "sensor_type", "detection_datetime"),
    )


class AISTrack(Base):
    """
    A single AIS position report, stored in PostGIS.
    """
    __tablename__ = "ais_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mmsi = Column(BigInteger, nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    sog = Column(Float, nullable=True)
    cog = Column(Float, nullable=True)

    # PostGIS point for the AIS report position
    geom = Column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_ais_mmsi_time", "mmsi", "timestamp"),
        UniqueConstraint("mmsi", "timestamp", name="uq_ais_mmsi_timestamp"),
    )


class ImageChip(Base):
    """
    Reference to a cropped detection image stored in MinIO.
    """
    __tablename__ = "image_chips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    detection_id = Column(Integer, nullable=False, index=True)
    image_name = Column(String(512), nullable=False)
    sensor_type = Column(String(8), nullable=False)
    minio_key = Column(Text, nullable=False)

    # Spatial reference for the chip
    center = Column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AISVessel(Base):
    """
    Vessel identity data extracted from AIS messages.
    """
    __tablename__ = "ais_vessels"

    mmsi = Column(BigInteger, primary_key=True, index=True)
    vessel_name = Column(String(512), nullable=True)
    vessel_type = Column(String(255), nullable=True)


class ProcessedImage(Base):
    """
    Tracking for satellite product names that have already been processed.
    Used to avoid duplicate automatic ingestion.
    """
    __tablename__ = "processed_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_name = Column(String(512), unique=True, nullable=False, index=True)
    sensor_type = Column(String(8), nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
