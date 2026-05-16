# Road User Intelligence Platform

Road User Intelligence Platform is a camera-based traffic analytics MVP focused on zebra-crossing safety and live traffic operations.

It can:
- detect and classify road users from video
- estimate speed
- count directional crossings across configured lines
- flag safety events such as zebra-crossing conflicts, stop-line events, speeding, and rider overload
- capture evidence snapshots for safety events
- let an operator draw counting lines and zebra-crossing bounds before analysis
- surface live analytics in a dashboard

## MVP Demo Path

For the strongest MVP flow, use the backend-served dashboard and the sample-video pipeline.

1. Start the sample MVP pipeline:

```bash
cd /Users/a2.0/Desktop/Road-User-Intelligence-Platform
bash run_pipeline.sh
```

2. Open the real dashboard surface:

- [http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/)

3. If you are adding a new camera or video first, use the `Setup` page in the dashboard to:
- load a frame from the source
- draw counting lines
- draw zebra-crossing bounds
- save the camera profile into [config/cameras.yaml](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/config/cameras.yaml)

Do not present the raw file copy at:

- [src/dashboard/app/index.html](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/src/dashboard/app/index.html)

That `file://` page is useful for editing, but the real MVP runs through the backend so live analytics, evidence, and camera state work correctly.

## Live Device Path

If you want to connect a live `reCamera` or other edge device, use:

```bash
cd /Users/a2.0/Desktop/Road-User-Intelligence-Platform
bash scripts/start_central_stack.sh
```

Then run the edge agent on the device and validate it with:

```bash
bash scripts/check_live_pipeline.sh http://127.0.0.1:8000 recam_01
```

More detail is in:

- [docs/live_validation_guide.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/live_validation_guide.md)

## Configuration

The main runtime configuration source for the core system is:

- [config/cameras.yaml](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/config/cameras.yaml)

This file defines:
- camera profiles
- calibration
- speed thresholds
- safety-event tuning
- zebra / stop-line / pedestrian zones
- counting lines
- live preview metadata

Additional files in `config/` such as:
- [config/traffic_count_line.yaml](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/config/traffic_count_line.yaml)
- [config/zebra_zone.yaml](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/config/zebra_zone.yaml)
- [config/zebra_zones.yaml](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/config/zebra_zones.yaml)

are calibration or analysis helpers, not the main authoritative runtime config for the live MVP.

## Core Docs

- [docs/demo_guide.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/demo_guide.md)
- [docs/deployment_guide.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/deployment_guide.md)
- [docs/installation_and_deployment.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/installation_and_deployment.md)
- [docs/system_architecture.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/system_architecture.md)

## Current MVP Focus

The platform is general traffic intelligence, but the current deployment focus is:

- zebra-crossing safety
- pedestrian conflict detection
- stop-line behavior
- directional traffic flow counting
- speed monitoring near crossing approaches

## Verification

Run the test suite with:

```bash
cd /Users/a2.0/Desktop/Road-User-Intelligence-Platform
source .venv/bin/activate
export PYTHONPATH=$PWD/src
python -m unittest discover -s tests -v
```

## Known MVP Limits

- Live camera viewing is snapshot-based today, not full streaming video transport.
- Safety-event quality depends on camera placement, calibration, and detection quality.
- The dashboard is intended to be served by the backend, not opened directly from disk.
