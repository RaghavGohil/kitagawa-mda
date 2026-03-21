#!/bin/bash
set -e

# Navigate to backend (required for alembic.ini to be found)
cd /app/backend

# Run migrations
echo "Running database migrations..."
alembic upgrade head

# Start the application
echo "Starting backend server..."
exec "$@"
