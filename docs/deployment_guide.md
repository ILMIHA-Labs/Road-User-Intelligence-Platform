# Deployment Guide

This guide describes the recommended deployment model for the public
research-reference MVP.

## Recommended layout

Use a split deployment:

- each `reCamera` or edge node runs only the edge vision producer
- one central server runs the broker, backend, analytics services, and
  dashboard

`reCamera` is optional. The software also supports generic file, webcam, and
RTSP inputs.

## 1. Install the repo

```bash
git clone <your-repo-url> /opt/road-user-platform
cd /opt/road-user-platform
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

## 2. Configure cameras

The authoritative runtime configuration is:

- `config/cameras.yaml`

This file defines:

- camera profiles
- calibration
- thresholds
- counting lines
- zones
- preview metadata

Helper files in `config/` are calibration or reference assets and should not be
treated as the primary runtime source of truth.

## 3. Configure environment files

Use the example files in `deploy/env`:

- `deploy/env/edge-vision.env.example`
- `deploy/env/server-common.env.example`

Important variables include:

- `MQTT_BROKER_HOST`
- `MQTT_BROKER_PORT`
- `BACKEND_API_URL`
- `BACKEND_HOST`
- `BACKEND_PORT`
- `CAMERA_CONFIG_PATH`
- `DATABASE_URL`
- `EVIDENCE_CAPTURE_ENABLED`
- `VIOLATION_EVIDENCE_RETENTION_SECONDS`
- `LIVE_PREVIEW_RETENTION_SECONDS`
- `SETUP_PREVIEW_RETENTION_SECONDS`

## Privacy-sensitive runtime defaults

The public release is conservative by default:

- `EVIDENCE_CAPTURE_ENABLED=false`
- previews are treated as short-lived runtime artifacts
- raw video retention is not part of the default backend behavior

If a deployment enables evidence capture or retains images for longer, that
decision should be documented and reviewed by the deployer.

## 4. Start the central stack

```bash
cd /opt/road-user-platform
source .venv/bin/activate
bash scripts/start_central_stack.sh
```

The script prints the exact backend and dashboard URL it is serving.

## 5. Start an edge source

Example with a generic local source:

```bash
cd /opt/road-user-platform
source .venv/bin/activate
export PYTHONPATH=$PWD/src:$PWD/src/edge_vision
python src/edge_vision/main.py --camera-id recam_01 --broker <server-ip> --source 0
```

Example with a video file:

```bash
python src/edge_vision/main.py --camera-id demo_cam --broker <server-ip> --source /path/to/video.mp4
```

## 6. Validate a running camera

```bash
bash scripts/check_live_pipeline.sh http://127.0.0.1:${BACKEND_PORT:-8000} recam_01
```

## 7. Responsible deployment notes

Before field deployment, review:

- `PRIVACY_POLICY.md`
- `SECURITY.md`
- `docs/data_governance.md`
- `docs/safety_and_risk.md`
