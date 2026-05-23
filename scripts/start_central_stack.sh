#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
MQTT_PORT="${MQTT_PORT:-1883}"
EVIDENCE_CAPTURE_ENABLED="${EVIDENCE_CAPTURE_ENABLED:-false}"
LIVE_PREVIEW_RETENTION_SECONDS="${LIVE_PREVIEW_RETENTION_SECONDS:-86400}"
SETUP_PREVIEW_RETENTION_SECONDS="${SETUP_PREVIEW_RETENTION_SECONDS:-86400}"
VIOLATION_EVIDENCE_RETENTION_SECONDS="${VIOLATION_EVIDENCE_RETENTION_SECONDS:-604800}"

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv in $ROOT_DIR"
  exit 1
fi

source .venv/bin/activate
export PYTHONPATH="$ROOT_DIR/src"
export EVIDENCE_CAPTURE_ENABLED
export LIVE_PREVIEW_RETENTION_SECONDS
export SETUP_PREVIEW_RETENTION_SECONDS
export VIOLATION_EVIDENCE_RETENTION_SECONDS

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

lsof -ti :"$MQTT_PORT" | xargs kill -9 2>/dev/null || true
lsof -ti :"$BACKEND_PORT" | xargs kill -9 2>/dev/null || true

mkdir -p logs
cat > logs/mosquitto.conf <<'MOSQUITTO_CONF'
listener __MQTT_PORT__ 0.0.0.0
allow_anonymous true
MOSQUITTO_CONF
sed -i.bak "s/__MQTT_PORT__/${MQTT_PORT}/" logs/mosquitto.conf && rm -f logs/mosquitto.conf.bak

echo "Starting MQTT broker on ${MQTT_PORT}..."
mosquitto -c logs/mosquitto.conf > logs/mqtt.log 2>&1 &
MQTT_PID=$!
sleep 2

echo "Starting backend API on ${BACKEND_HOST}:${BACKEND_PORT}..."
uvicorn src.backend_api.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" > logs/backend.log 2>&1 &
API_PID=$!
sleep 2

echo "Starting MQTT forwarder..."
python src/data_streaming/mqtt_forwarder.py --broker 127.0.0.1 --port "$MQTT_PORT" --api "http://127.0.0.1:${BACKEND_PORT}" > logs/streaming.log 2>&1 &
STREAM_PID=$!

echo "Starting speed estimation..."
python src/speed_estimation/main.py --broker 127.0.0.1 --port "$MQTT_PORT" --config config/cameras.yaml > logs/speed.log 2>&1 &
SPEED_PID=$!

echo "Starting violation detection..."
python src/violation_detection/main.py --broker 127.0.0.1 --port "$MQTT_PORT" --config config/cameras.yaml > logs/violation.log 2>&1 &
VIOL_PID=$!

echo
echo "Central stack is up."
echo "Backend:   http://127.0.0.1:${BACKEND_PORT}/"
echo "Dashboard: http://127.0.0.1:${BACKEND_PORT}/dashboard/"
echo "Logs:      $ROOT_DIR/logs/"
echo "Evidence capture enabled: ${EVIDENCE_CAPTURE_ENABLED}"
echo
echo "Connect the reCamera to this machine's IP as its MQTT broker."
echo "Press Ctrl+C when you're done."

wait "$MQTT_PID" "$API_PID" "$STREAM_PID" "$SPEED_PID" "$VIOL_PID"
