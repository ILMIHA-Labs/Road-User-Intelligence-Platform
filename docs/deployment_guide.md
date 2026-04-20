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

cameras:
  - id: recam_01
    location: north_gate
    target_fps: 15
    pixels_per_meter: 21.0
    speed_limit_kmh: 40.0

  - id: recam_02
    location: school_zone
    target_fps: 12
    pixels_per_meter: 18.5
    speed_limit_kmh: 30.0
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
