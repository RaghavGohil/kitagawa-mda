#!/bin/bash
set -e

# Ensure we are in /app so uvicorn can find the 'backend' package
cd /app

# Start the application
echo "Starting backend server..."
exec "$@"
