#!/usr/bin/env bash

# Exit on error
set -o errexit

echo "Starting Background Worker..."
# Start Celery worker in the background
# We limit concurrency to 1 to save memory on the 512MB free tier
celery -A config worker --concurrency=1 -l info &

echo "Starting Web Server..."
# Start Uvicorn to handle both HTTP and WebSockets
uvicorn config.asgi:application --host 0.0.0.0 --port ${PORT:-8000}
