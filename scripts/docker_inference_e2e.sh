#!/bin/bash
set -e

echo "Starting E2E Inference Orchestration Script..."

# Set environment variables for testing
export POSTGRES_DB=image_scoring_test
export WEBUI_OPEN_UI=0
export IMAGE_SCORING_DOCKER_INFERENCE_E2E=1
export RUN_POSTGRES_TESTS=1

# Ensure the test database exists and initialize tables
echo "Preparing test database..."
python3 -c "
from modules.db_postgres import ensure_database_exists, truncate_app_tables
from modules.db import init_db

ensure_database_exists('image_scoring_test')
init_db()

# Truncate tables for a clean slate
truncate_app_tables()
"

# Start the WebUI in the background
echo "Starting WebUI..."
python3 webui.py &
WEBUI_PID=$!

# Set up trap to kill the WebUI process on exit
trap "echo 'Cleaning up WebUI process...'; kill $WEBUI_PID 2>/dev/null || true" EXIT

# Wait for readiness
echo "Waiting for WebUI to become ready..."
MAX_RETRIES=30
COUNT=0
READY=0
until [ $COUNT -eq $MAX_RETRIES ]; do
    if curl -s -f http://127.0.0.1:7860/mcp-status > /dev/null; then
        READY=1
        break
    fi
    echo "Still waiting for WebUI (attempt $((COUNT+1))/$MAX_RETRIES)..."
    sleep 2
    COUNT=$(( COUNT + 1 ))
done

if [ $READY -eq 0 ]; then
    echo "WebUI failed to start or become ready in time."
    exit 1
fi

echo "WebUI is ready! Running E2E tests..."

# Run pytest on the new E2E module
pytest tests/e2e_docker/test_inference_via_live_api.py -v -m "inference_e2e"

echo "E2E Inference Tests completed successfully."
