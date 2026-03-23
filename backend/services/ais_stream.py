"""
AISStream.io WebSocket ingest service.

Connects to the aisstream.io WebSocket API, subscribes to specific
bounding boxes, and ingests real-time position reports into PostGIS.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import websockets
from sqlalchemy import text

from backend.db.connection import async_session
from shared.config import AISSTREAM_API_KEY, AISSTREAM_BBOX

# Batching settings
BATCH_SIZE = 50
FLUSH_INTERVAL_S = 10


class _AISStreamState:
    """Internal state for the AIS stream background task."""

    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.total_messages = 0
        self.errors = 0
        self.last_message_time: Optional[datetime] = None
        self._last_errors: list[str] = []
        self.started_at: Optional[datetime] = None
        self.current_bboxes: Optional[list] = None  # Current active subscription
        self._listeners: set[asyncio.Queue] = set()
        self._restart_event = asyncio.Event()

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to live AIS messages. Returns a queue."""
        q = asyncio.Queue(maxsize=100)
        self._listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """Unsubscribe from live AIS messages."""
        if q in self._listeners:
            self._listeners.remove(q)

    def broadcast(self, message: dict):
        """Push a message to all active listeners."""
        # Clean up full queues if necessary
        dead_listeners = []
        for q in self._listeners:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                dead_listeners.append(q)

        for q in dead_listeners:
            self.unsubscribe(q)

    async def update_bboxes(self, bboxes: list):
        """Update active bboxes (disabled re-subscription for stability)."""
        self.current_bboxes = bboxes
        if self.running:
            # We no longer trigger self._restart_event.set() here to avoid WebSocket churn.
            # Subscription is now fixed to global/large area on startup.
            print(
                "[AIS Stream] Area updated in memory, but subscription remains stable."
            )

    def status(self) -> dict:
        return {
            "running": self.running,
            "total_messages": self.total_messages,
            "errors": self.errors,
            "last_message_time": self.last_message_time.isoformat()
            if self.last_message_time
            else None,
            "last_errors": self._last_errors,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "active_bboxes": self.current_bboxes,
            "listeners": len(self._listeners),
        }


_state = _AISStreamState()


def get_status() -> dict:
    """Current status of the live AIS WebSocket stream."""
    return _state.status()


def subscribe() -> asyncio.Queue:
    """Subscribe to live AIS messages."""
    return _state.subscribe()


def unsubscribe(q: asyncio.Queue):
    """Unsubscribe from live AIS messages."""
    _state.unsubscribe(q)


async def set_active_bboxes(bboxes: list):
    """Update the active subscription area."""
    await _state.update_bboxes(bboxes)


def start():
    """Start the live AIS WebSocket listener as a background task."""
    if _state.running:
        return {"status": "already running"}

    if not AISSTREAM_API_KEY:
        print("[AIS Stream] FAILED: AISSTREAM_API_KEY not configured.")
        return {"status": "error", "message": "API Key missing"}

    _state.running = True
    _state.started_at = datetime.now(timezone.utc)
    _state.task = asyncio.create_task(_run_loop())
    print("[AIS Stream] Background task started.")
    return {"status": "started"}


def stop():
    """Stop the live AIS task."""
    if not _state.running:
        return {"status": "not running"}

    _state.running = False
    if _state.task:
        _state.task.cancel()
    print("[AIS Stream] Background task stopped.")
    return {"status": "stopped"}


async def _run_loop():
    """Main ingestion loop with automatic reconnection and Area Tuning."""
    # Use a stable, high-traffic default area (Singapore) to avoid area-limit kicks.
    # Total area: ~6,000 km² (Limit is 100,000 km² for standard keys)
    _state.current_bboxes = [[[1.0, 103.5], [1.5, 104.5]]]

    if AISSTREAM_BBOX:
        try:
            _state.current_bboxes = json.loads(AISSTREAM_BBOX)
        except (json.JSONDecodeError, TypeError):
            pass

    backoff = 1.0
    while _state.running:
        try:
            await _connect_and_ingest()
            # If it returns normally, it means it was requested to stop or re-tune
            if not _state._restart_event.is_set():
                backoff = 1.0  # Reset backoff on successful run
            else:
                await asyncio.sleep(0.5)  # Quick turnaround for area tuning
        except Exception as e:
            _state.errors += 1
            err_msg = f"Connection error: {e}"
            print(f"[AIS Stream] {err_msg}")
            _state._last_errors.append(err_msg)
            if len(_state._last_errors) > 5:
                _state._last_errors.pop(0)

            await asyncio.sleep(backoff)
            backoff = min(60.0, backoff * 2)


async def _connect_and_ingest():
    """Connect to WebSocket and process messages until closed or restart requested."""
    # 1. Prepare batches
    track_batch = []
    vessel_batch = {}  # mmsi -> {name, type}

    _state._restart_event.clear()

    async with websockets.connect(
        "wss://stream.aisstream.io/v0/stream",
        ping_interval=10,
        ping_timeout=10,
        close_timeout=5,
    ) as ws:
        # 2. Subscribe to bboxes in ONE message (preferred by AISStream.io)
        bboxes = _state.current_bboxes or [[[-90, -180], [90, 180]]]
        subscribe_msg = {
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": bboxes,  # Already a 3rd-level array: [[[lat, lon], [lat, lon]]]
        }
        await ws.send(json.dumps(subscribe_msg))
        print(f"[AIS Stream] Connected and subscribed to {len(bboxes)} box(es).")

        # 3. Process messages
        # We use a combined waiter for ws.recv() and periodic flushes
        status_task = asyncio.create_task(asyncio.sleep(30))
        batch_task = asyncio.create_task(asyncio.sleep(FLUSH_INTERVAL_S))
        restart_task = asyncio.create_task(_state._restart_event.wait())
        recv_task = asyncio.create_task(ws.recv())

        # Keep track of active tasks in a set for asyncio.wait
        active_tasks = {status_task, batch_task, restart_task, recv_task}

        try:
            while _state.running:
                done, pending = await asyncio.wait(
                    active_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                # Keep pending tasks for the next iteration
                active_tasks = pending

                if restart_task in done:
                    print(
                        "[AIS Stream] Restart event (area tune) received. Reconnecting..."
                    )
                    break

                for task in done:
                    if task == status_task:
                        status_task = asyncio.create_task(asyncio.sleep(30))
                        active_tasks.add(status_task)
                    elif task == batch_task:
                        batch_task = asyncio.create_task(
                            asyncio.sleep(FLUSH_INTERVAL_S)
                        )
                        active_tasks.add(batch_task)
                        if track_batch or vessel_batch:
                            # Capture and Clear: prevents race condition during DB await
                            tracks_to_flush = list(track_batch)
                            vessels_to_flush = dict(vessel_batch)
                            track_batch.clear()
                            vessel_batch.clear()
                            await _flush_to_db(tracks_to_flush, vessels_to_flush)

                    elif task == recv_task:
                        try:
                            raw_msg = task.result()
                            # Recreate recv_task and add to active set
                            recv_task = asyncio.create_task(ws.recv())
                            active_tasks.add(recv_task)
                            await _handle_message(raw_msg, track_batch, vessel_batch)
                        except (
                            websockets.exceptions.ConnectionClosed,
                            websockets.exceptions.WebSocketException,
                        ) as e:
                            err_msg = f"External WebSocket closed: {e}"
                            print(f"[AIS Stream] {err_msg}")
                            _state._last_errors.append(err_msg)
                            return  # Reconnect
                        except Exception as e:
                            print(f"[AIS Stream] Message error: {e}")
                            recv_task = asyncio.create_task(ws.recv())
                            active_tasks.add(recv_task)

                if len(track_batch) >= BATCH_SIZE:
                    # Capture and Clear: ensures no data loss during flush
                    tracks_to_flush = list(track_batch)
                    vessels_to_flush = dict(vessel_batch)
                    track_batch.clear()
                    vessel_batch.clear()
                    await _flush_to_db(tracks_to_flush, vessels_to_flush)

        finally:
            # Clean up all active tasks
            for task in active_tasks:
                task.cancel()


async def _handle_message(raw_msg, track_batch, vessel_batch):
    """Parse and route individual AIS message."""
    try:
        msg = json.loads(raw_msg)
    except json.JSONDecodeError:
        return

    _state.total_messages += 1
    _state.last_message_time = datetime.now(timezone.utc)

    # Note: We support PositionReport (1, 2, 3) and ShipStaticData (5)
    msg_type = msg.get("MessageType")
    if msg_type not in ["PositionReport", "ShipStaticData"]:
        return

    mmsi = msg.get("MetaData", {}).get("MMSI")
    if not mmsi:
        return

    # Extract dynamic data
    pos = msg.get("Message", {}).get("PositionReport", {})
    lat = pos.get("Latitude")
    lon = pos.get("Longitude")
    cog = pos.get("TrueHeading") or pos.get("CourseOverGround")
    sog = pos.get("SpeedOverGround")
    ts_str = msg.get("MetaData", {}).get("time_utc")

    if lat is None or lon is None or ts_str is None:
        return

    # Parse timestamp: "2024-05-15 12:34:56.789 +0000 UTC"
    # The format might vary slightly, let's use a robust parser
    try:
        # Simple cleanup of trailing UTC etc if present
        clean_ts = ts_str.split(" +")[0].split(" UTC")[0].strip()
        ts = datetime.fromisoformat(clean_ts).replace(tzinfo=timezone.utc)
    except Exception:
        ts = datetime.now(timezone.utc)

    track_batch.append(
        {
            "mmsi": mmsi,
            "timestamp": ts,
            "geom": f"SRID=4326;POINT({lon} {lat})",
            "sog": float(sog or 0),
            "cog": float(cog or 0),
        }
    )

    # Update metadata if available
    vessel_data = msg.get("MetaData")
    static_msg = msg.get("Message", {}).get("ShipStaticData", {})

    v_name = None
    v_type = None

    if vessel_data or static_msg:
        v_name = (
            vessel_data.get("ShipName", "").strip()
            if vessel_data
            else static_msg.get("Name", "").strip()
        )
        v_type = vessel_data.get("ShipType") if vessel_data else static_msg.get("Type")

        vessel_batch[mmsi] = {
            "vessel_name": v_name,
            "vessel_type": v_type,
            "imo": str(static_msg.get("Imo") or ""),
            "callsign": static_msg.get("CallSign", "").strip(),
            "length": float(
                static_msg.get("Dimension", {}).get("A", 0)
                + static_msg.get("Dimension", {}).get("B", 0)
            ),
            "width": float(
                static_msg.get("Dimension", {}).get("C", 0)
                + static_msg.get("Dimension", {}).get("D", 0)
            ),
            "draught": float(static_msg.get("MaximumStaticDraught", 0)),
            "destination": static_msg.get("Destination", "").strip(),
            "eta": f"{static_msg.get('Eta', {}).get('Month', 0)}-{static_msg.get('Eta', {}).get('Day', 0)} {static_msg.get('Eta', {}).get('Hour', 0)}:{static_msg.get('Eta', {}).get('Minute', 0)} UTC",
            "last_sog": float(sog or 0),
            "last_cog": float(cog or 0),
        }

    # Broadcast translated message to frontend listeners (now with metadata)
    _state.broadcast(
        {
            "mmsi": mmsi,
            "timestamp": ts.isoformat(),
            "sog": float(sog or 0),
            "cog": float(cog or 0),
            "lat": float(lat),
            "lon": float(lon),
            "name": v_name,
            "type": v_type,
        }
    )


async def _flush_to_db(track_batch, vessel_batch):
    """Batch insert tracks and upsert vessel metadata."""
    if not track_batch and not vessel_batch:
        return

    async with async_session() as db:
        try:
            # 1. Update/Upsert Vessels (Batched)
            vessel_params = [
                {
                    "mmsi": m,
                    "vessel_name": d["vessel_name"],
                    "vessel_type": d["vessel_type"],
                    "imo": d["imo"],
                    "callsign": d["callsign"],
                    "length": d["length"],
                    "width": d["width"],
                    "draught": d["draught"],
                    "destination": d["destination"],
                    "eta": d["eta"],
                    "sog": d.get("last_sog", 0),
                    "cog": d.get("last_cog", 0),
                }
                for m, d in vessel_batch.items()
                if d["vessel_name"] or d["imo"]
            ]

            if vessel_params:
                upsert_sql = """
                    INSERT INTO ais_vessels (
                        mmsi, vessel_name, vessel_type, imo, callsign, 
                        length, width, draught, destination, eta, last_seen,
                        last_sog, last_cog
                    )
                    VALUES (
                        :mmsi, :vessel_name, :vessel_type, :imo, :callsign, 
                        :length, :width, :draught, :destination, :eta, NOW(),
                        :sog, :cog
                    )
                    ON CONFLICT (mmsi) DO UPDATE SET
                        vessel_name = COALESCE(NULLIF(EXCLUDED.vessel_name, ''), ais_vessels.vessel_name),
                        vessel_type = COALESCE(EXCLUDED.vessel_type, ais_vessels.vessel_type),
                        imo = COALESCE(NULLIF(EXCLUDED.imo, '0'), NULLIF(EXCLUDED.imo, ''), ais_vessels.imo),
                        callsign = COALESCE(NULLIF(EXCLUDED.callsign, ''), ais_vessels.callsign),
                        length = COALESCE(NULLIF(EXCLUDED.length, 0), ais_vessels.length),
                        width = COALESCE(NULLIF(EXCLUDED.width, 0), ais_vessels.width),
                        draught = COALESCE(NULLIF(EXCLUDED.draught, 0), ais_vessels.draught),
                        destination = COALESCE(NULLIF(EXCLUDED.destination, ''), ais_vessels.destination),
                        eta = COALESCE(NULLIF(EXCLUDED.eta, '0-0 0:0 UTC'), ais_vessels.eta),
                        last_sog = EXCLUDED.last_sog,
                        last_cog = EXCLUDED.last_cog,
                        last_seen = NOW()
                """
                await db.execute(text(upsert_sql), vessel_params)

            if track_batch:
                insert_sql = """
                    INSERT INTO ais_tracks (mmsi, timestamp, geom, sog, cog)
                    VALUES (:mmsi, :timestamp, ST_GeomFromEWKT(:geom), :sog, :cog)
                """
                await db.execute(text(insert_sql), track_batch)

            await db.commit()
            # print(f"[AIS Stream] Flushed {len(track_batch)} points and {len(vessel_batch)} vessels.")
        except Exception as e:
            await db.rollback()
            print(f"[AIS Stream] Flush error: {e}")
