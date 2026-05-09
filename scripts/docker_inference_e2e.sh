#!/bin/bash
set -e

echo "Starting E2E Inference Orchestration Script..."

# Set environment variables for testing
export POSTGRES_DB=image_scoring_test
export WEBUI_OPEN_UI=0
export IMAGE_SCORING_DOCKER_INFERENCE_E2E=1
export RUN_POSTGRES_TESTS=1

# Ensure the test database is completely fresh
echo "Recreating test database..."
export PYTHONPATH=.
cat <<EOF > /tmp/recreate_db.py
import psycopg2
import os
import sys

host = os.environ.get("POSTGRES_HOST", "db-e2e")
user = os.environ.get("POSTGRES_USER", "postgres")
password = os.environ.get("POSTGRES_PASSWORD", "postgres")

try:
    conn = psycopg2.connect(host=host, user=user, password=password, dbname="postgres")
    conn.autocommit = True
    cur = conn.cursor()

    # Kill connections to the test DB
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'image_scoring_test' AND pid <> pg_backend_pid()")

    cur.execute("DROP DATABASE IF EXISTS image_scoring_test")
    cur.execute("CREATE DATABASE image_scoring_test")
    conn.close()
    print("Database image_scoring_test recreated.")
except Exception as e:
    print(f"Failed to recreate database: {e}")
    # Don't exit here, maybe it's fine
EOF
python3 /tmp/recreate_db.py

echo "Initializing database schema..."
python3 -c "from modules.db import init_db; init_db()"

# Start the WebUI in the background
echo "Starting WebUI..."
python3 webui.py > /app/webui_docker.log 2>&1 &
WEBUI_PID=$!

# Set up trap to kill the WebUI process on exit
trcleanup() {
    echo "Cleaning up WebUI process..."
    if [ ! -z "$WEBUI_PID" ]; then
        kill $WEBUI_PID || true
    fi
    echo "--- WEBUI LOG START ---"
    cat /app/webui_docker.log || true
    echo "--- WEBUI LOG END ---"
    cp /app/webui_docker.log /app/tests/webui_docker_test.log || true
}
trap trcleanup EXIT

# Wait for readiness
echo "Waiting for WebUI to become ready..."
MAX_RETRIES=30
COUNT=0
READY=0
until [ $COUNT -eq $MAX_RETRIES ]; do
    if curl -s -f http://127.0.0.1:7860/api/health > /dev/null; then
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

# Ensure httpx is available for the test script
pip install httpx

# Run pytest on the new E2E module
pytest tests/e2e_docker/test_inference_via_live_api.py -v -m "inference_e2e"

echo "E2E Inference Tests completed successfully."
