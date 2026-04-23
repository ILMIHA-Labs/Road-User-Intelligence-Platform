# Live Validation Guide

This guide is for validating one real `reCamera` against the current MVP pipeline.

## Goal

Confirm that one physical camera can:

1. publish detection events
2. produce speed estimates
3. trigger violations
4. appear in the backend and dashboard

## What to run on the central machine

Use the helper script:

```bash
cd /Users/a2.0/Desktop/Road-User-Intelligence-Platform
bash scripts/start_central_stack.sh
```

This starts:

- Mosquitto on `1883`
- FastAPI backend on `8000`
- MQTT forwarder
- speed estimation
- violation detection

The dashboard will be available at:

- `http://127.0.0.1:8000/dashboard/`

## What to run on the reCamera

On the device:

```bash
cd /opt/road-user-platform
source .venv/bin/activate
export PYTHONPATH=$PWD/src
python src/edge_vision/main.py --camera-id recam_01 --broker <central-machine-ip> --source 0
```

Use the correct source:

- `0` for a local camera device
- an RTSP URL if the camera is exposed that way
- another device index if needed

## How to validate quickly

Once the edge agent is running, on the central machine run:

```bash
bash scripts/check_live_pipeline.sh http://127.0.0.1:8000 recam_01
```

You should start seeing:

- `total_detections_logged` increasing
- recent detections in `/events/recent`
- speeds after enough movement is observed
- violations when the rule conditions are met

## What success looks like

At minimum:

- backend root responds
- `recam_01` appears in `/analytics/summary`
- `/events/recent?camera_id=recam_01` contains detections

Stronger success:

- `/events/recent` contains speeds
- `/analytics/violations` shows real rule activity
- dashboard cards update for the live camera

## What to check if detections do not appear

1. Can the reCamera reach the MQTT broker IP?
2. Is the edge agent logging successful broker connection?
3. Is the backend stack running on the central machine?
4. Are there errors in:
   - `logs/mqtt.log`
   - `logs/backend.log`
   - `logs/streaming.log`
   - `logs/speed.log`
   - `logs/violation.log`

## What to check if detections appear but no speeds do

1. The tracked object may not have moved enough between frames.
2. `pixels_per_meter` may need tuning in `config/cameras.yaml`.
3. Confirm the camera ID in the edge agent matches the camera profile.

## What to check if speeds appear but no violations do

1. The configured `speed_limit_kmh` may be too high.
2. Helmet status is currently only as good as the upstream detection signal.
3. `multiple_riders_violation` depends on pedestrian-to-motorcycle association and may need camera-specific tuning.

## Suggested first field test

1. Start the central stack.
2. Start one reCamera with `camera_id=recam_01`.
3. Walk through the frame and confirm detections arrive.
4. Ride or simulate a motorcycle through frame to confirm tracking.
5. Confirm the camera appears in the dashboard.
6. Tune camera config after the first run.
