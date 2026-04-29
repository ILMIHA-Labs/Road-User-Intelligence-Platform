#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv in $ROOT_DIR"
  exit 1
fi

source .venv/bin/activate
export PYTHONPATH="$ROOT_DIR/src"

cleanup() {
  echo
  echo "Stopping central stack..."
  for pid in "${VIOL_PID:-}" "${SPEED_PID:-}" "${STREAM_PID:-}" "${API_PID:-}" "${MQTT_PID:-}"; do
    if [[ -n "${pid}" ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup EXIT INT TERM

lsof -ti :1883 | xargs kill -9 2>/dev/null || true
lsof -ti :8000 | xargs kill -9 2>/dev/null || true

mkdir -p logs
cat > logs/mosquitto.conf <<'MOSQUITTO_CONF'
listener 1883 0.0.0.0
allow_anonymous true
MOSQUITTO_CONF

echo "Starting MQTT broker on 1883..."
mosquitto -c logs/mosquitto.conf > logs/mqtt.log 2>&1 &
MQTT_PID=$!
sleep 2

echo "Starting backend API on 0.0.0.0:8000..."
uvicorn src.backend_api.main:app --host 0.0.0.0 --port 8000 > logs/backend.log 2>&1 &
API_PID=$!
sleep 2

echo "Starting MQTT forwarder..."
python src/data_streaming/mqtt_forwarder.py > logs/streaming.log 2>&1 &
STREAM_PID=$!

echo "Starting speed estimation..."
python src/speed_estimation/main.py > logs/speed.log 2>&1 &
SPEED_PID=$!

echo "Starting violation detection..."
python src/violation_detection/main.py > logs/violation.log 2>&1 &
VIOL_PID=$!

echo
echo "Central stack is up."
echo "Backend:   http://127.0.0.1:8000/"
echo "Dashboard: http://127.0.0.1:8000/dashboard/"
echo "Logs:      $ROOT_DIR/logs/"
echo
echo "Connect the reCamera to this machine's IP as its MQTT broker."
echo "Press Ctrl+C when you're done."

wait "$MQTT_PID" "$API_PID" "$STREAM_PID" "$SPEED_PID" "$VIOL_PID"
