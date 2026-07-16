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

Any demo-oriented camera profile in `config/cameras.yaml` should be treated as a
template that must be pointed at a licensed local source by the operator.

## 3. Configure environment files

Use the example files in `deploy/env`:

- `deploy/env/edge-vision.env.example`
- `deploy/env/server-common.env.example`

Important variables include:

- `RUIP_API_KEY` — bearer token required on all API requests. Leave unset in local dev to skip auth. Set to a strong random value in any networked deployment (e.g. `openssl rand -hex 32`).
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
- `LIVE_CLIP_RETENTION_SECONDS`
- `VIDEO_ANALYSIS_RETENTION_SECONDS`
- `VIDEO_ANALYSIS_MAX_UPLOAD_MB`
- `VIDEO_ANALYSIS_MAX_CONCURRENT_JOBS`
- `ALERTS_ENABLED`, `ALERT_WEBHOOK_URL`, `ALERT_VIOLATION_TYPES`, and the
  camera-health thresholds (see "Alerting & camera health" below)

## Alerting & camera health

The backend can notify operators when a safety violation fires or when a camera
stops publishing. Alerting is **disabled by default** (`ALERTS_ENABLED=false`)
and is delivered over a webhook and/or an MQTT topic. Every alert is also
recorded to the `alerts` table and is queryable at `GET /api/v1/alerts`.

```bash
ALERTS_ENABLED=true
ALERT_WEBHOOK_URL=https://your-endpoint.example/road-user-alerts
ALERT_VIOLATION_TYPES=            # empty = all supported types
ALERT_DEBOUNCE_SECONDS=60         # min gap between same camera+type alerts
CAMERA_OFFLINE_AFTER_SECONDS=60   # no activity for this long => offline alert
CAMERA_HEALTH_POLL_SECONDS=30     # how often the health monitor checks
ALERT_CAMERA_RECOVERY_ENABLED=true
# Optional MQTT delivery (reuses MQTT_BROKER_HOST / MQTT_BROKER_PORT):
ALERT_MQTT_ENABLED=false
ALERT_MQTT_TOPIC=alerts/events
```

Verify configuration and delivery:

```bash
curl http://127.0.0.1:8000/api/v1/alerts/config   # effective config, secrets redacted
curl -X POST http://127.0.0.1:8000/api/v1/alerts/test   # fire a test alert
```

Alert payloads carry **event-level metadata only** (camera id, event type,
timestamp) — never imagery or personal data — consistent with the platform's
privacy posture. If a delivery channel fails, the alert is still recorded with
the error; it never blocks event ingest.

## Privacy-sensitive runtime defaults

The public release is conservative by default:

- `EVIDENCE_CAPTURE_ENABLED=false`
- previews are treated as short-lived runtime artifacts
- dashboard-uploaded video analysis sessions expire after the configured
  temporary-analysis retention period
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

## Alternative: Docker Compose

Instead of the systemd + virtualenv path above, the repository also ships a
`docker-compose.yml` that runs the mosquitto broker, backend API, and all
worker services (edge vision, speed estimation, violation detection, MQTT
forwarder) as containers on a single host. This is useful for evaluators who
want a single-command stack without managing a Python virtualenv or systemd
units directly.

```bash
cp deploy/env/server-common.env.example deploy/env/server-common.env
cp deploy/env/edge-vision.env.example deploy/env/edge-vision.env
# edit deploy/env/edge-vision.env: point EDGE_SOURCE at a licensed video file
# mounted under ./data (e.g. EDGE_SOURCE=/data/demo.mp4), or a webcam device
docker compose up --build
```

The dashboard is served at `http://localhost:8000/dashboard/`. `config/`
is mounted read-only into every service so edits to `config/cameras.yaml` on
the host take effect on container restart.

By default the backend uses a SQLite database stored in the `db-data` named
volume. A commented-out `postgres` service (Compose profile `postgres`) is
included in `docker-compose.yml` for operators who want a server-grade
database; see the comments in that file before enabling it.

This Docker path is an alternative to, not a replacement for, the systemd
deployment above — both read the same `deploy/env/*.env` files and
`config/cameras.yaml`.

## 7. Responsible deployment notes

Before field deployment, review:

- `PRIVACY_POLICY.md`
- `SECURITY.md`
- `docs/data_governance.md`
- `docs/safety_and_risk.md`
- `docs/dpg_submission_checklist.md`
