"""
Shared configuration loaded from environment variables.
Used by both inference server and backend server.
"""

import os


# ---------------------------------------------------------------------------
# PostGIS
# ---------------------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "kitagawa")
POSTGRES_USER = os.getenv("POSTGRES_USER", "kitagawa")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "kitagawa")

DATABASE_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

DATABASE_URL_SYNC = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# ---------------------------------------------------------------------------
# MinIO
# ---------------------------------------------------------------------------
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "kitagawa-chips")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Inference server
# ---------------------------------------------------------------------------
INFERENCE_SERVER_URL = os.getenv("INFERENCE_SERVER_URL", "http://inference-server:8001")

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DATA_DIR = os.getenv("DATA_DIR", "/data")
IMAGES_DIR = os.path.join(DATA_DIR, "inference_images")
AIS_DIR = os.path.join(DATA_DIR, "AIS")
DETECTIONS_DIR = os.path.join(DATA_DIR, "detections")
MASK_DIR = os.getenv("MASK_DIR", "/app/landmask")

# ---------------------------------------------------------------------------
# Copernicus credentials (for image download)
# ---------------------------------------------------------------------------
COPERNICUS_USERNAME = os.getenv("COPERNICUS_USERNAME", "")
COPERNICUS_PASSWORD = os.getenv("COPERNICUS_PASSWORD", "")

# ---------------------------------------------------------------------------
# AISStream.io (real-time AIS via WebSocket)
# ---------------------------------------------------------------------------
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY", "")
# Bounding boxes as JSON string: [[[-90,-180],[90,180]]] = entire world
AISSTREAM_BBOX = os.getenv("AISSTREAM_BBOX", "[[[-90,-180],[90,180]]]")
# Enable/disable live AIS on startup (default: auto-start if key is set)
AISSTREAM_AUTO_START = os.getenv("AISSTREAM_AUTO_START", "true").lower() == "true"
