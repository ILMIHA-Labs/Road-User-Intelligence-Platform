# Deployment Guide

This guide describes the recommended MVP deployment model for the Road User Intelligence Platform.

## Recommended MVP Layout

Use a split deployment:

- Each `reCamera` runs only the edge vision producer.
- One central server runs the rest of the pipeline.

### Edge devices

Each `reCamera` should run:

- `src/edge_vision/main.py`

Each device publishes detection events to the shared MQTT broker.

### Central server

The central server should run:

- `mosquitto`
- `src/backend_api.main:app`
- `src/data_streaming/mqtt_forwarder.py`
- `src/speed_estimation/main.py`
- `src/violation_detection/main.py`

The backend dashboard is served at `/dashboard/`.

## Why this layout

This is the safest way to get the MVP working:

- edge devices stay lightweight
- backend and database stay centralized
- speed and violation logic use one shared event stream
- adding new cameras mostly becomes a config task

## 1. Install the repo

Clone the repo onto each device and the central server:

```bash
git clone <your-repo-url> /opt/road-user-platform
cd /opt/road-user-platform
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure cameras

Set camera-specific profiles in [config/cameras.yaml](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/config/cameras.yaml):

```yaml
defaults:
  pixels_per_meter: 25.0
  speed_limit_kmh: 60.0
  speed_tolerance_kmh: 0.0
  severe_speed_delta_kmh: 20.0
  speed_reset_delta_kmh: 5.0
  stopped_speed_threshold_kmh: 3.0
  stopped_duration_seconds: 20
  stopped_resume_speed_kmh: 8.0
  max_motorcycle_riders: 2
  rider_association_window_seconds: 2.0
  rider_horizontal_margin_ratio: 0.35
  rider_upper_margin_ratio: 0.75
  rider_lower_margin_ratio: 0.25

cameras:
  - id: recam_01
    location: north_gate
    target_fps: 15
    pixels_per_meter: 21.0
    speed_limit_kmh: 40.0
    speed_tolerance_kmh: 2.0
    severe_speed_delta_kmh: 15.0
    stopped_duration_seconds: 12
    max_motorcycle_riders: 2

  - id: recam_02
    location: school_zone
    target_fps: 12
    pixels_per_meter: 18.5
    speed_limit_kmh: 30.0
    speed_tolerance_kmh: 1.0
    severe_speed_delta_kmh: 10.0
    stopped_duration_seconds: 10
    max_motorcycle_riders: 2
```

## 3. Configure environment files

Copy the example files from [deploy/env](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/deploy/env):

- `edge-vision.env.example` for each reCamera
- `server-common.env.example` for the central server

Suggested install location:

- `/etc/road-user-platform/edge-vision.env`
- `/etc/road-user-platform/server-common.env`

Important variables:

- `MQTT_BROKER_HOST`
- `MQTT_BROKER_PORT`
- `BACKEND_API_URL`
- `CAMERA_CONFIG_PATH`
- `DATABASE_URL`
- `CAMERA_ID`
- `EDGE_SOURCE`
- `DEFAULT_SPEED_TOLERANCE_KMH`
- `SEVERE_SPEED_DELTA_KMH`
- `SPEED_RESET_DELTA_KMH`
- `STOPPED_SPEED_THRESHOLD_KMH`
- `STOPPED_DURATION_SECONDS`
- `STOPPED_RESUME_SPEED_KMH`
- `MAX_MOTORCYCLE_RIDERS`
- `RIDER_ASSOCIATION_WINDOW_SECONDS`
- `RIDER_HORIZONTAL_MARGIN_RATIO`
- `RIDER_UPPER_MARGIN_RATIO`
- `RIDER_LOWER_MARGIN_RATIO`

## Violation tuning fields

You can override violation thresholds per camera in `config/cameras.yaml`.

- `speed_tolerance_kmh`: tolerance before a speed violation triggers
- `severe_speed_delta_kmh`: extra speed above threshold to mark severe speeding
- `speed_reset_delta_kmh`: amount below threshold required before the same object can trigger again
- `stopped_speed_threshold_kmh`: maximum speed still treated as stationary
- `stopped_duration_seconds`: how long a vehicle must remain stopped before a violation is emitted
- `stopped_resume_speed_kmh`: speed above which a stopped state resets
- `max_motorcycle_riders`: maximum allowed riders on a motorcycle
- `rider_association_window_seconds`: maximum timestamp gap for rider-to-motorcycle association
- `rider_horizontal_margin_ratio`: horizontal expansion around a motorcycle when linking riders
- `rider_upper_margin_ratio`: how far above the motorcycle a rider center may be
- `rider_lower_margin_ratio`: how far below the motorcycle a rider center may be

## 4. Bring up the central server

Install Mosquitto:

```bash
sudo apt-get update
sudo apt-get install -y mosquitto mosquitto-clients
```

Start the central services manually first:

```bash
cd /opt/road-user-platform
source .venv/bin/activate
export PYTHONPATH=$PWD/src

mosquitto -p 1883
```

In separate terminals:

```bash
cd /opt/road-user-platform
source .venv/bin/activate
export PYTHONPATH=$PWD/src
uvicorn src.backend_api.main:app --host 0.0.0.0 --port 8000
```

```bash
cd /opt/road-user-platform
source .venv/bin/activate
export PYTHONPATH=$PWD/src
python src/data_streaming/mqtt_forwarder.py
```

```bash
cd /opt/road-user-platform
source .venv/bin/activate
export PYTHONPATH=$PWD/src
python src/speed_estimation/main.py
```

```bash
cd /opt/road-user-platform
source .venv/bin/activate
export PYTHONPATH=$PWD/src
python src/violation_detection/main.py
```

Then open:

- `http://<server-ip>:8000/`
- `http://<server-ip>:8000/dashboard/`

## 5. Bring up each reCamera

On each device:

```bash
cd /opt/road-user-platform
source .venv/bin/activate
export PYTHONPATH=$PWD/src
python src/edge_vision/main.py --camera-id recam_01 --broker <server-ip> --source 0
```

If the device uses an RTSP URL instead of camera index `0`, pass that in `--source`.

## 6. Install systemd services

Service templates are in [deploy/systemd](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/deploy/systemd).

Copy them into `/etc/systemd/system/` and reload systemd:

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Enable on the server:

```bash
sudo systemctl enable --now road-user-backend.service
sudo systemctl enable --now road-user-forwarder.service
sudo systemctl enable --now road-user-speed.service
sudo systemctl enable --now road-user-violation.service
```

Enable on each reCamera:

```bash
sudo systemctl enable --now road-user-edge-vision.service
```

## 7. Verify the deployment

On the server:

```bash
sudo systemctl status road-user-backend.service
sudo systemctl status road-user-forwarder.service
sudo systemctl status road-user-speed.service
sudo systemctl status road-user-violation.service
```

On each edge device:

```bash
sudo systemctl status road-user-edge-vision.service
```

Check logs with:

```bash
journalctl -u road-user-edge-vision.service -f
journalctl -u road-user-backend.service -f
```

## 8. MVP rollout order

1. Deploy the central server.
2. Connect one reCamera.
3. Confirm detections arrive.
4. Confirm speed and violation events persist.
5. Open the dashboard and verify counts change.
6. Add more cameras one at a time.
7. Tune `pixels_per_meter` and `speed_limit_kmh` per camera.

## Notes

- [run_pipeline.sh](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/run_pipeline.sh) is for local development, not field deployment.
- The backend currently defaults to SQLite for the MVP.
- For production scale, you will likely want PostgreSQL and stronger service supervision.
