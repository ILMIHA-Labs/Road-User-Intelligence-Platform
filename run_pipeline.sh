#!/usr/bin/env bash

# Activate virtual environment
source venv/bin/activate

export PYTHONPATH=$PWD/src

echo "============================================="
echo "Starting Road User Intelligence Platform MVP"
echo "============================================="

# 1. Start MQTT Broker
echo "Starting MQTT Broker (amqtt) on port 1883..."
amqtt -c mqtt_broker.yaml > mqtt.log 2>&1 &
MQTT_PID=$!
sleep 2

# 2. Start Backend API
echo "Starting Backend API on port 8000..."
uvicorn backend_api.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
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

sleep 2

# 6. Start Edge Vision Agent in foreground to show video
echo "Starting Edge Vision Agent processing sample.mp4..."
echo "Press 'q' in the video window to stop."
python src/edge_vision/main.py --source data/sample.mp4 --show

echo "============================================="
echo "Stopping all services..."
echo "============================================="
kill $VIOL_PID
kill $SPEED_PID
kill $STREAM_PID
kill $API_PID
kill $MQTT_PID
echo "Done."
