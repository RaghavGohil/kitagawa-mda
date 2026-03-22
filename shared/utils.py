"""
Shared utilities for resource monitoring and general helpers.
"""

import shutil
import os
import psutil
from datetime import datetime, timezone


def parse_iso_datetime(iso_str: str) -> datetime:
    """Parse ISO 8601 string to aware UTC datetime."""
    if not iso_str:
        return datetime.now(timezone.utc)
    try:
        # Replace Z with +00:00 for older python compatibility if needed
        # but 3.11+ handles Z fine.
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def get_free_disk_gb(path: str) -> float:
    """Return free disk space in GB at the given path."""
    total, used, free = shutil.disk_usage(path)
    return free / (1024**3)


def get_memory_usage_mb() -> float:
    """Return current process memory usage in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def check_resources(
    min_disk_gb: float = 2.0, max_mem_pct: float = 98.0
) -> tuple[bool, str]:
    """
    Check if enough resources are available.
    Returns (success, message).
    """
    try:
        # Disk check
        data_dir = os.getenv("DATA_DIR", "/data")
        if not os.path.exists(data_dir):
            data_dir = "."

        free_gb = get_free_disk_gb(data_dir)
        if free_gb < min_disk_gb:
            return (
                False,
                f"Low disk space: {free_gb:.2f} GB free (min {min_disk_gb} GB)",
            )

        # Memory check
        mem = psutil.virtual_memory()
        if mem.percent > max_mem_pct:
            return False, f"High memory usage: {mem.percent}% (max {max_mem_pct}%)"

        return True, "Resources OK"
    except Exception as e:
        print(f"[Resources] Error checking: {e}")
        # Allow if check itself fails (e.g. psutil issue in some containers)
        return True, "Resources OK (check failed)"
