#!/usr/bin/env bash

# Activate virtual environment
source .venv/bin/activate

export PYTHONPATH=$PWD/src

# Kill any stale processes from a previous run
lsof -ti :1883 | xargs kill -9 2>/dev/null || true
lsof -ti :8000 | xargs kill -9 2>/dev/null || true

echo "============================================="
echo "Starting Road User Intelligence Platform MVP"
echo "============================================="

# 1. Start MQTT Broker (mosquitto)
echo "Starting MQTT Broker (mosquitto) on port 1883..."
mosquitto -p 1883 > mqtt.log 2>&1 &
MQTT_PID=$!
sleep 2   # give broker time to bind port 1883

# 2. Start Backend API
echo "Starting Backend API on port 8000..."
uvicorn src.backend_api.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
API_PID=$!
sleep 2

# 3. Start Streaming Agent
echo "Starting Data Streaming Agent..."
python src/data_streaming/mqtt_forwarder.py > streaming.log 2>&1 &
STREAM_PID=$!

# 4. Start Speed Estimation Agent
echo "Starting Speed Estimation Agent..."
python src/speed_estimation/main.py > speed.log 2>&1 &
SPEED_PID=$!

# 5. Start Violation Detection Agent
echo "Starting Violation Detection Agent..."
python src/violation_detection/main.py > violation.log 2>&1 &
VIOL_PID=$!

sleep 1

# 6. Start Edge Vision Agent in foreground to show video
echo "Starting Edge Vision Agent processing sample.mp4..."
echo "Press 'q' in the video window to stop."
python src/edge_vision/main.py --source data/sample.mp4 --camera-id sample_video_01 --show || true

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
echo "Dashboard available at: http://127.0.0.1:8000/dashboard"
echo "Run 'kill $API_PID' to stop the backend when done."
