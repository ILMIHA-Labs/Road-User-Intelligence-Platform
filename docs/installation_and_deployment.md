# Installation and Deployment Guide

This guide covers local setup for researchers and the default MVP deployment
flow.

## 1. Prerequisites

- Python 3.9+
- macOS or Linux shell
- Git
- Optional system MQTT broker fallback: Mosquitto

## 2. Clone and environment setup

```bash
git clone https://github.com/ILMIHA-Labs/Road-User-Intelligence-Platform.git
cd Road-User-Intelligence-Platform
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
export PYTHONPATH=$PWD/src
```

## 3. Verify the installation

```bash
python -m unittest discover -s tests -v
```

## 4. Run the local MVP

Provide a licensed local video source or camera source.

```bash
export DEMO_VIDEO_SOURCE=/absolute/path/to/your/video.mp4
bash run_pipeline.sh
```

The script prints the exact backend and dashboard URL it is serving.

## 5. Live deployment topology

- Edge device: edge vision capture, detect, and publish
- Central server: MQTT broker, backend API, speed estimation, safety-event
  detection, dashboard

## 6. Privacy-aware defaults

The public release defaults are conservative:

- `EVIDENCE_CAPTURE_ENABLED=false`
- preview and setup-preview artifacts are short-lived runtime files
- raw video is not archived by the backend by default

If you change these defaults for a deployment, update your local policy and
retention settings as well.

## 7. Troubleshooting

- If the startup script fails, inspect the log files it prints.
- If a dashboard route returns `Not Found`, confirm the expected backend port.
- If evidence does not appear, confirm that `EVIDENCE_CAPTURE_ENABLED=true` was
  intentionally set.
