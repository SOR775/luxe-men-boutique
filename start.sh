#!/usr/bin/env bash

# Exit on error
set -o errexit

echo "Creating necessary directories..."
mkdir -p logs

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Background Worker..."
# Start Celery worker in the background
# We limit concurrency to 1 to save memory on the 512MB free tier
celery -A config worker --concurrency=1 -l info &

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "Seeding products..."
  python seed_data.py
else
  echo "Skipping seed step (set RUN_SEED=true to run it)."
fi

echo "Starting Web Server..."
# Start Uvicorn to handle both HTTP and WebSockets
uvicorn config.asgi:application --host 0.0.0.0 --port ${PORT:-8000}