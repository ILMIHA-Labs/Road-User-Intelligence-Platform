# Installation and Deployment Guide

This guide covers local setup and MVP deployment flow for the Road User Intelligence Platform.

## 1. Prerequisites

- Python 3.9+
- macOS/Linux shell
- Git
- Optional system MQTT broker fallback: Mosquitto

## 2. Clone and Environment Setup

```bash
git clone https://github.com/ILMIHA-Labs/Road-User-Intelligence-Platform.git
cd Road-User-Intelligence-Platform
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. MQTT Broker Setup

The pipeline startup script attempts broker startup with this order:

1. `amqtt`
2. `python -m amqtt`
3. `mosquitto` fallback using `mosquitto.conf`

If you want system Mosquitto on macOS:

```bash
brew install mosquitto
```

## 4. Run the MVP Pipeline

```bash
source .venv/bin/activate
bash run_pipeline.sh
```

Services started by pipeline script:

- MQTT broker
- Backend API
- Data streaming forwarder
- Speed estimation agent
- Violation detection agent
- Edge vision pipeline

## 5. Verify Persistence

```bash
sqlite3 road_user_platform.db "select 'detections', count(*) from detections union all select 'speeds', count(*) from speeds union all select 'violations', count(*) from violations union all select 'trajectories', count(*) from trajectories;"
```

## 6. Deployment Topology (MVP)

- Edge device: edge vision capture/detect/publish
- Server/GPU node: speed estimation, violation detection, trajectory prediction
- Backend node: MQTT broker, API, database, data engineering

## 7. ReCamera Edge Rollout

For staged ReCamera deployment, follow:

- `docs/recamera_deployment_plan.md`
- `docs/recamera_runtime_audit.md`
- `docs/recamera_runtime_audit_results.md`

## 8. Troubleshooting

If startup fails, inspect logs at repository root:

- `mqtt.log`
- `backend.log`
- `streaming.log`
- `speed.log`
- `violation.log`

If broker startup fails due to Python dependency constraints, install Mosquitto and rerun pipeline.
