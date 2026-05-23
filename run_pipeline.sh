#!/usr/bin/env bash

set -u

PIDS=()
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
MQTT_PORT="${MQTT_PORT:-1883}"
DEMO_VIDEO_SOURCE="${DEMO_VIDEO_SOURCE:-data/sample.mp4}"
DEMO_CAMERA_ID="${DEMO_CAMERA_ID:-sample_video_01}"
BACKEND_BASE_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"

check_service_started() {
	local pid="$1"
	local name="$2"
	local logfile="$3"

	if ! kill -0 "$pid" 2>/dev/null; then
		echo "Error: ${name} failed to start. Last log lines from ${logfile}:"
		tail -n 20 "$logfile" 2>/dev/null || echo "(No log output found)"
		exit 1
	fi
}

cleanup() {
	echo "============================================="
	echo "Stopping all services..."
	echo "============================================="

	if (( ${#PIDS[@]} > 0 )); then
		for pid in "${PIDS[@]}"; do
			if kill -0 "$pid" 2>/dev/null; then
				kill "$pid" 2>/dev/null || true
			fi
		done
	fi

	echo "Done."
}

trap cleanup EXIT

# Activate virtual environment
if [[ -f "venv/bin/activate" ]]; then
	source venv/bin/activate
elif [[ -f ".venv/bin/activate" ]]; then
	source .venv/bin/activate
elif [[ -f "src/venv/bin/activate" ]]; then
	source src/venv/bin/activate
else
	echo "Error: Virtual environment not found. Checked venv/bin/activate, .venv/bin/activate, and src/venv/bin/activate"
	exit 1
fi

if command -v python >/dev/null 2>&1; then
	PY_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
	PY_BIN="$(command -v python3)"
else
	echo "Error: Python interpreter not found (python/python3)."
	exit 1
fi

if ! "$PY_BIN" -c "import fastapi, paho.mqtt.client, requests" >/dev/null 2>&1; then
	echo "Error: Missing Python dependencies. Run: pip install -r requirements.txt"
	exit 1
fi

export PYTHONPATH=$PWD/src
export EVIDENCE_CAPTURE_ENABLED="${EVIDENCE_CAPTURE_ENABLED:-false}"
export LIVE_PREVIEW_RETENTION_SECONDS="${LIVE_PREVIEW_RETENTION_SECONDS:-86400}"
export SETUP_PREVIEW_RETENTION_SECONDS="${SETUP_PREVIEW_RETENTION_SECONDS:-86400}"
export VIOLATION_EVIDENCE_RETENTION_SECONDS="${VIOLATION_EVIDENCE_RETENTION_SECONDS:-604800}"

# Kill any stale processes from a previous run
lsof -ti :"$MQTT_PORT" | xargs kill -9 2>/dev/null || true
lsof -ti :"$BACKEND_PORT" | xargs kill -9 2>/dev/null || true

if [[ ! -f "$DEMO_VIDEO_SOURCE" ]]; then
	echo "Error: Demo video source not found: $DEMO_VIDEO_SOURCE"
	echo "Provide a licensed local clip with:"
	echo "  export DEMO_VIDEO_SOURCE=/absolute/path/to/your/video.mp4"
	exit 1
fi

echo "============================================="
echo "Starting Road User Intelligence Platform MVP"
echo "============================================="

# 1. Start MQTT Broker
echo "Starting MQTT Broker on port ${MQTT_PORT}..."
BROKER_STARTED=0
if command -v amqtt >/dev/null 2>&1; then
	amqtt -c mqtt_broker.yaml > mqtt.log 2>&1 &
	MQTT_PID=$!
	sleep 2
	if kill -0 "$MQTT_PID" 2>/dev/null; then
		BROKER_STARTED=1
	else
		echo "Warning: amqtt failed to start, trying mosquitto fallback..."
	fi
elif "$PY_BIN" -m amqtt --help >/dev/null 2>&1; then
	"$PY_BIN" -m amqtt -c mqtt_broker.yaml > mqtt.log 2>&1 &
	MQTT_PID=$!
	sleep 2
	if kill -0 "$MQTT_PID" 2>/dev/null; then
		BROKER_STARTED=1
	else
		echo "Warning: python -m amqtt failed to start, trying mosquitto fallback..."
	fi
fi

if (( BROKER_STARTED == 0 )); then
	if command -v mosquitto >/dev/null 2>&1; then
		echo "Using mosquitto fallback broker."
		mosquitto -c mosquitto.conf > mqtt.log 2>&1 &
		MQTT_PID=$!
		sleep 2
		check_service_started "$MQTT_PID" "MQTT Broker" "mqtt.log"
		BROKER_STARTED=1
	else
		echo "Error: No MQTT broker found. Install amqtt (pip install amqtt) or mosquitto (brew install mosquitto)."
		exit 1
	fi
fi

PIDS+=("$MQTT_PID")

# 2. Start Backend API
echo "Starting Backend API on ${BACKEND_HOST}:${BACKEND_PORT}..."
if command -v uvicorn >/dev/null 2>&1; then
	uvicorn backend_api.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" > backend.log 2>&1 &
else
	"$PY_BIN" -m uvicorn backend_api.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" > backend.log 2>&1 &
fi
API_PID=$!
PIDS+=("$API_PID")
sleep 2
check_service_started "$API_PID" "Backend API" "backend.log"

# 3. Start Streaming Agent
echo "Starting Data Streaming Agent..."
"$PY_BIN" src/data_streaming/mqtt_forwarder.py --broker 127.0.0.1 --port "$MQTT_PORT" --api "$BACKEND_BASE_URL" > streaming.log 2>&1 &
STREAM_PID=$!
PIDS+=("$STREAM_PID")
sleep 1
check_service_started "$STREAM_PID" "Data Streaming Agent" "streaming.log"

# 4. Start Speed Estimation Agent
echo "Starting Speed Estimation Agent..."
"$PY_BIN" src/speed_estimation/main.py --broker 127.0.0.1 --port "$MQTT_PORT" --config config/cameras.yaml > speed.log 2>&1 &
SPEED_PID=$!
PIDS+=("$SPEED_PID")
sleep 1
check_service_started "$SPEED_PID" "Speed Estimation Agent" "speed.log"

# 5. Start Violation Detection Agent
echo "Starting Violation Detection Agent..."
"$PY_BIN" src/violation_detection/main.py --broker 127.0.0.1 --port "$MQTT_PORT" --config config/cameras.yaml > violation.log 2>&1 &
VIOL_PID=$!
PIDS+=("$VIOL_PID")
sleep 1
check_service_started "$VIOL_PID" "Violation Detection Agent" "violation.log"

sleep 1

# 6. Start Edge Vision Agent in foreground to show video
echo "Starting Edge Vision Agent processing ${DEMO_VIDEO_SOURCE}..."
echo "Press 'q' in the video window to stop."
"$PY_BIN" src/edge_vision/main.py --source "$DEMO_VIDEO_SOURCE" --camera-id "$DEMO_CAMERA_ID" --broker 127.0.0.1 --port "$MQTT_PORT" --camera-config config/cameras.yaml --show || true

echo "Video complete. Waiting for streaming agent to flush events..."
sleep 5   # let MQTT forwarder finish writing remaining events to the backend

echo "============================================="
echo "Stopping pipeline agents..."
echo "============================================="
kill "$VIOL_PID"   2>/dev/null || true
kill "$SPEED_PID"  2>/dev/null || true
kill "$STREAM_PID" 2>/dev/null || true
kill "$MQTT_PID"   2>/dev/null || true
echo "Agents stopped. Backend API kept alive (PID $API_PID)."
echo ""
echo "Backend available at: ${BACKEND_BASE_URL}/"
echo "Dashboard available at: ${BACKEND_BASE_URL}/dashboard/"
echo "Run 'kill $API_PID' to stop the backend when done."
