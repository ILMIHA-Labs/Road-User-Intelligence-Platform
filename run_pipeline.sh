#!/usr/bin/env bash

set -u

PIDS=()

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
elif [[ -f "src/venv/bin/activate" ]]; then
	source src/venv/bin/activate
else
	echo "Error: Virtual environment not found. Checked venv/bin/activate and src/venv/bin/activate"
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

echo "============================================="
echo "Starting Road User Intelligence Platform MVP"
echo "============================================="

# 1. Start MQTT Broker
echo "Starting MQTT Broker (amqtt) on port 1883..."
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
echo "Starting Backend API on port 8000..."
if command -v uvicorn >/dev/null 2>&1; then
	uvicorn backend_api.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
else
	"$PY_BIN" -m uvicorn backend_api.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
fi
API_PID=$!
PIDS+=("$API_PID")
sleep 2
check_service_started "$API_PID" "Backend API" "backend.log"

# 3. Start Streaming Agent
echo "Starting Data Streaming Agent..."
"$PY_BIN" src/data_streaming/mqtt_forwarder.py > streaming.log 2>&1 &
STREAM_PID=$!
PIDS+=("$STREAM_PID")
sleep 1
check_service_started "$STREAM_PID" "Data Streaming Agent" "streaming.log"

# 4. Start Speed Estimation Agent
echo "Starting Speed Estimation Agent..."
"$PY_BIN" src/speed_estimation/main.py > speed.log 2>&1 &
SPEED_PID=$!
PIDS+=("$SPEED_PID")
sleep 1
check_service_started "$SPEED_PID" "Speed Estimation Agent" "speed.log"

# 5. Start Violation Detection Agent
echo "Starting Violation Detection Agent..."
"$PY_BIN" src/violation_detection/main.py > violation.log 2>&1 &
VIOL_PID=$!
PIDS+=("$VIOL_PID")
sleep 1
check_service_started "$VIOL_PID" "Violation Detection Agent" "violation.log"

sleep 2

# 6. Start Edge Vision Agent in foreground to show video
echo "Starting Edge Vision Agent processing sample.mp4..."
echo "Press 'q' in the video window to stop."
"$PY_BIN" src/edge_vision/main.py --source data/sample.mp4 --show
