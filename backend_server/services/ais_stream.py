"""
Real-time AIS ingestion via AISStream.io WebSocket.

Connects to the AISStream.io WebSocket API and continuously ingests
PositionReport and ShipStaticData messages into the existing
ais_tracks / ais_vessels tables.

This runs alongside the existing NOAA batch AIS system — both data
sources write to the same tables.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

import websockets
from sqlalchemy import text

from backend_server.db.connection import async_session
from shared.config import AISSTREAM_API_KEY, AISSTREAM_BBOX

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WS_URL = "wss://stream.aisstream.io/v0/stream"
BATCH_SIZE = 100  # Flush to DB every N messages
FLUSH_INTERVAL_S = 5.0  # Or every N seconds, whichever comes first
RECONNECT_BASE_S = 2.0  # Exponential backoff base
RECONNECT_MAX_S = 120.0  # Max backoff
STATS_LOG_INTERVAL_S = 60.0  # Log stats every N seconds


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class _AISStreamState:
    """Mutable singleton tracking the live AIS stream state."""

    def __init__(self):
        self.running: bool = False
        self.connected: bool = False
        self.task: Optional[asyncio.Task] = None
        self.total_messages: int = 0
        self.total_inserted: int = 0
        self.last_message_time: Optional[datetime] = None
        self.errors: int = 0
        self.started_at: Optional[datetime] = None

    def status(self) -> dict:
        return {
            "running": self.running,
            "connected": self.connected,
            "total_messages": self.total_messages,
            "total_inserted": self.total_inserted,
            "errors": self.errors,
            "last_message_time": (
                self.last_message_time.isoformat() if self.last_message_time else None
            ),
            "started_at": (self.started_at.isoformat() if self.started_at else None),
            "api_key_set": bool(AISSTREAM_API_KEY),
        }


_state = _AISStreamState()


# ---------------------------------------------------------------------------
# Public control API
# ---------------------------------------------------------------------------
def get_status() -> dict:
    """Current status of the live AIS stream."""
    return _state.status()


def start():
    """Start the live AIS WebSocket listener as a background task."""
    if _state.running:
        return {"status": "already_running"}
    if not AISSTREAM_API_KEY:
        return {"status": "error", "detail": "AISSTREAM_API_KEY is not set"}

    _state.running = True
    _state.started_at = datetime.now(timezone.utc)
    _state.task = asyncio.create_task(_stream_loop())
    print("[AISStream] Started live AIS ingestion.")
    return {"status": "started"}


def stop():
    """Stop the live AIS WebSocket listener."""
    if not _state.running:
        return {"status": "already_stopped"}

    _state.running = False
    if _state.task and not _state.task.done():
        _state.task.cancel()
    print("[AISStream] Stopped live AIS ingestion.")
    return {"status": "stopped"}


# ---------------------------------------------------------------------------
# Core WebSocket loop
# ---------------------------------------------------------------------------
async def _stream_loop():
    """
    Main loop: connect → subscribe → ingest → reconnect on failure.
    Uses exponential backoff for reconnection.
    """
    backoff = RECONNECT_BASE_S

    while _state.running:
        try:
            await _connect_and_ingest()
            # If we return cleanly, reset backoff
            backoff = RECONNECT_BASE_S
        except asyncio.CancelledError:
            print("[AISStream] Task cancelled.")
            break
        except Exception as e:
            _state.errors += 1
            _state.connected = False
            print(
                f"[AISStream] Connection error: {e}. Reconnecting in {backoff:.0f}s..."
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX_S)

    _state.connected = False
    _state.running = False


async def _connect_and_ingest():
    """Single connection session: subscribe + ingest loop."""
    # Parse bounding boxes from config
    try:
        bboxes = json.loads(AISSTREAM_BBOX)
    except (json.JSONDecodeError, TypeError):
        bboxes = [[[-90, -180], [90, 180]]]

    async with websockets.connect(WS_URL, ping_interval=30, ping_timeout=10) as ws:
        # Send subscription within 3 seconds (API requirement)
        subscribe_msg = {
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": bboxes,
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
        }
        await ws.send(json.dumps(subscribe_msg))
        _state.connected = True
        print(f"[AISStream] Connected and subscribed (bbox={bboxes}).")

        # Ingestion buffers
        track_batch: list[dict] = []
        vessel_batch: dict[int, dict] = {}
        last_flush = time.monotonic()
        last_stats = time.monotonic()

        async for raw_msg in ws:
            if not _state.running:
                break

            try:
                msg = json.loads(raw_msg)
            except json.JSONDecodeError:
                continue

            # Handle errors from the server
            if "error" in msg:
                print(f"[AISStream] Server error: {msg['error']}")
                _state.errors += 1
                continue

            _state.total_messages += 1
            _state.last_message_time = datetime.now(timezone.utc)

            msg_type = msg.get("MessageType", "")
            meta = msg.get("MetaData", {})
            message = msg.get("Message", {})

            if msg_type == "PositionReport":
                pos = message.get("PositionReport", {})
                mmsi = meta.get("MMSI")
                if not mmsi:
                    continue

                # Extract timestamp — use metadata time_utc or fall back to now
                ts_str = meta.get("time_utc", "")
                try:
                    # Format: "2022-12-29 18:22:32.318353 +0000 UTC"
                    ts = datetime.strptime(
                        ts_str.rsplit(" UTC", 1)[0].strip(), "%Y-%m-%d %H:%M:%S.%f %z"
                    )
                except (ValueError, IndexError):
                    try:
                        ts = datetime.strptime(
                            ts_str.rsplit(" UTC", 1)[0].strip(), "%Y-%m-%d %H:%M:%S %z"
                        )
                    except (ValueError, IndexError):
                        ts = datetime.now(timezone.utc)

                lat = pos.get("Latitude", meta.get("latitude"))
                lon = pos.get("Longitude", meta.get("longitude"))
                if lat is None or lon is None:
                    continue

                track_batch.append(
                    {
                        "mmsi": int(mmsi),
                        "ts": ts,
                        "sog": float(pos.get("Sog", 0) or 0),
                        "cog": float(pos.get("Cog", 0) or 0),
                        "lon": float(lon),
                        "lat": float(lat),
                    }
                )

                # Also capture vessel name from metadata if available
                ship_name = meta.get("ShipName", "").strip()
                if ship_name and ship_name != "":
                    vessel_batch[int(mmsi)] = {
                        "mmsi": int(mmsi),
                        "vname": ship_name[:512],
                        "vtype": None,
                    }

            elif msg_type == "ShipStaticData":
                static = message.get("ShipStaticData", {})
                mmsi = meta.get("MMSI")
                if not mmsi:
                    continue

                name = static.get("Name", "").strip()
                if name:
                    vessel_batch[int(mmsi)] = {
                        "mmsi": int(mmsi),
                        "vname": name[:512],
                        "vtype": str(static.get("Type", ""))[:255] or None,
                    }

            # Flush to database if batch is full or interval elapsed
            now = time.monotonic()
            if len(track_batch) >= BATCH_SIZE or (now - last_flush) >= FLUSH_INTERVAL_S:
                if track_batch or vessel_batch:
                    await _flush_to_db(track_batch, vessel_batch)
                    track_batch.clear()
                    vessel_batch.clear()
                    last_flush = now

            # Periodic stats log
            if (now - last_stats) >= STATS_LOG_INTERVAL_S:
                print(
                    f"[AISStream] Stats: {_state.total_messages} msgs received, "
                    f"{_state.total_inserted} inserted, {_state.errors} errors"
                )
                last_stats = now

        # Flush remaining
        if track_batch or vessel_batch:
            await _flush_to_db(track_batch, vessel_batch)


# ---------------------------------------------------------------------------
# Database flush
# ---------------------------------------------------------------------------
async def _flush_to_db(
    tracks: list[dict],
    vessels: dict[int, dict],
):
    """Batch insert tracks and vessels into PostGIS."""
    try:
        async with async_session() as db:
            # Insert tracks (ON CONFLICT DO NOTHING for dedup)
            if tracks:
                for i in range(0, len(tracks), 5000):
                    sub = tracks[i : i + 5000]
                    await db.execute(
                        text("""
                            INSERT INTO ais_tracks (mmsi, timestamp, sog, cog, geom)
                            VALUES (:mmsi, :ts, :sog, :cog,
                                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
                            ON CONFLICT (mmsi, timestamp) DO NOTHING
                        """),
                        sub,
                    )
                _state.total_inserted += len(tracks)

            # Upsert vessels
            if vessels:
                vessel_list = list(vessels.values())
                for i in range(0, len(vessel_list), 5000):
                    sub = vessel_list[i : i + 5000]
                    await db.execute(
                        text("""
                            INSERT INTO ais_vessels (mmsi, vessel_name, vessel_type)
                            VALUES (:mmsi, :vname, :vtype)
                            ON CONFLICT (mmsi) DO UPDATE SET
                                vessel_name = COALESCE(EXCLUDED.vessel_name,
                                                       ais_vessels.vessel_name),
                                vessel_type = COALESCE(EXCLUDED.vessel_type,
                                                       ais_vessels.vessel_type)
                        """),
                        sub,
                    )

            await db.commit()
    except Exception as e:
        _state.errors += 1
        print(f"[AISStream] DB flush error: {e}")
