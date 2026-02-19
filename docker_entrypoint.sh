#!/bin/bash
set -eu

export PREFECT_API_URL="http://0.0.0.0:4200/api"

# --- Start Prefect server if not already running ---
if ! curl -fsS "${PREFECT_API_URL}/ready" >/dev/null 2>&1; then
    echo "[INFO] Starting Prefect server..."
    nohup prefect server start --host 0.0.0.0 --port 4200 &
else
    echo "[INFO] Prefect server already running."
fi

# --- Wait for Prefect server readiness ---
echo "[INFO] Waiting for Prefect server to become ready..."
for i in {1..60}; do
    if curl -fsS "${PREFECT_API_URL}/ready" >/dev/null 2>&1; then
        echo "[INFO] Prefect server is ready."
        break
    fi
    echo "[INFO] Waiting... (${i}s)"
    sleep 2
done

# --- Launch inference pipeline ---
echo "[INFO] Launching inference pipeline..."
python inference_pipeline.py

tail -f /dev/null