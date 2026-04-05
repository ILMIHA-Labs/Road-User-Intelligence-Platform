# ReCamera Edge Deployment Plan

## Goal

Deploy the platform to a reCamera as an edge detection device that publishes platform-compatible detection events to the central MQTT broker, while keeping heavier services off-device until the edge path is stable.

## Recommended Target Architecture

For the first productionable edge rollout, the reCamera should run only the edge capture, inference, and MQTT publish path.

On reCamera:

- `src/edge_vision/camera_capture.py`
- `src/edge_vision/detection.py`
- `src/edge_vision/publisher.py`
- `src/edge_vision/main.py`

Off-device on server or cloud:

- `src/speed_estimation/main.py`
- `src/violation_detection/main.py`
- `src/data_streaming/mqtt_forwarder.py`
- `src/backend_api/main.py`
- PostgreSQL and dashboard stack

This matches the current architecture in `docs/system_architecture.md` and avoids overloading the edge device with services that do not need to run on-camera.

## Key Constraint

The current edge implementation is desktop-oriented:

- it assumes generic Python package installation from `requirements.txt`
- it uses `opencv-python` and `ultralytics` directly
- it defaults to local display mode via OpenCV
- it assumes a stable MQTT connection with no offline queue

On reCamera, the first technical decision is whether Python + Ultralytics runs acceptably on-device, or whether inference should use the device-native stack and only adapt results into the project MQTT schema.

## Delivery Principle

Do not try to deploy the whole platform to reCamera in one branch.

Ship it in small branches with one acceptance target per PR:

1. prove runtime compatibility
2. make the edge agent configurable for device use
3. make it resilient enough for unattended execution
4. package it as a service
5. validate performance in field conditions
6. then continue with the rest of the platform hardening

## Git Workflow

Use `main` as the protected integration branch.

For every step below:

1. Update `main`
2. Create a short-lived feature branch from `main`
3. Implement only that phase's scope
4. Run relevant tests and a manual validation checklist
5. Open a PR into `main`
6. Merge only when acceptance criteria are met
7. Tag deployable milestones

Suggested branch naming:

- `feature/recamera-runtime-audit`
- `feature/recamera-edge-config`
- `feature/recamera-mqtt-resilience`
- `feature/recamera-service-packaging`
- `feature/edge-schema-contracts`
- `feature/pipeline-orchestration`
- `feature/speed-calibration-workflow`
- `feature/backend-hardening`
- `feature/observability-healthchecks`
- `release/recamera-pilot`
- `hotfix/recamera-*`

Suggested tags:

- `edge-v0.1-runtime-validated`
- `edge-v0.2-pilot-ready`
- `edge-v0.3-field-tested`
- `platform-v1.0.0`

## Phase 0: Baseline and Decision Gate

Branch: `feature/recamera-runtime-audit`

Purpose:

- establish what the reCamera can actually run from this codebase
- decide whether inference stays in Python or moves to the device-native AI runtime

Work:

- inspect reCamera OS version and update to current stable release
- verify SSH access, persistent storage path, and outbound network reachability to MQTT
- benchmark camera capture on-device
- benchmark current `ultralytics` model load and inference time if installable
- verify whether `opencv-python`, `numpy`, `scipy`, and `ultralytics` install cleanly on the target
- decide between:
  - Path A: keep `src/edge_vision/detection.py` on Python/Ultralytics
  - Path B: replace detection backend with reCamera-native model execution and keep the same MQTT event schema

Acceptance criteria:

- one written decision on Path A vs Path B
- measured FPS, CPU, memory, temperature, and boot time on device
- known install procedure for the chosen runtime

Git steps:

1. `git checkout main`
2. `git pull --ff-only`
3. `git checkout -b feature/recamera-runtime-audit`
4. commit benchmark notes, install instructions, and any probe scripts
5. open PR and merge after review

## Phase 1: Make Edge Vision Device-Configurable

Branch: `feature/recamera-edge-config`

Purpose:

- remove desktop-only assumptions from the edge agent

Work:

- move broker host, port, camera ID, source, model path, confidence threshold, and topic names into config or environment variables
- add a headless mode as the default for device execution
- separate local demo mode from device mode
- add reconnect-safe startup behavior if MQTT is temporarily unavailable
- make camera source selection explicit for reCamera hardware

Files likely affected:

- `src/edge_vision/main.py`
- `src/edge_vision/publisher.py`
- `src/edge_vision/camera_capture.py`
- `config/cameras.yaml`
- `requirements.txt`

Acceptance criteria:

- device can boot the edge agent without GUI requirements
- broker endpoint is configurable without code edits
- camera identity is stable and externally configurable

Git steps:

1. branch from updated `main`
2. keep the PR limited to edge configuration and startup changes
3. merge only after a smoke test against a remote MQTT broker

## Phase 2: MQTT and Event Resilience

Branch: `feature/recamera-mqtt-resilience`

Purpose:

- make the device safe to leave unattended on unstable networks

Work:

- add MQTT reconnect handling and publish result checks
- add optional local buffering for short broker outages
- standardize event timestamps and camera metadata
- add structured logging for connect, disconnect, dropped frame, and dropped publish events
- define what happens when inference succeeds but publish fails

Files likely affected:

- `src/edge_vision/publisher.py`
- `src/edge_vision/main.py`

Acceptance criteria:

- device recovers from broker restart without manual intervention
- publish failures are visible in logs and counters
- message payloads remain schema-compatible with downstream services

Git steps:

1. implement only resilience and telemetry changes
2. test with broker restarts and temporary network loss
3. merge after manual fault-injection evidence is recorded in the PR

## Phase 3: Package the Edge Agent for ReCamera

Branch: `feature/recamera-service-packaging`

Purpose:

- make deployment repeatable

Work:

- create a device installation script
- create an update script
- create a system service definition so the edge agent starts on boot
- define filesystem layout for logs, config, and model assets
- document secrets and configuration handling

Recommended device layout:

- application code in `/opt/road-user-intelligence`
- config in `/etc/road-user-intelligence`
- logs in `/var/log/road-user-intelligence`

Acceptance criteria:

- a clean device can be provisioned from documented steps
- service restarts automatically after reboot
- logs are available without attaching a display

Git steps:

1. branch from `main`
2. add packaging scripts and service files
3. merge after testing on a freshly provisioned or reset device

## Phase 4: Field Validation on ReCamera

Branch: `release/recamera-pilot`

Purpose:

- validate that the edge path works in realistic deployment conditions

Work:

- mount and orient the camera correctly
- validate day and night performance
- validate frame rate under expected traffic density
- measure thermal throttling risk
- verify end-to-end event delivery into MQTT and downstream services

Acceptance criteria:

- stable run for at least one extended pilot window
- acceptable FPS and drop rate for the chosen model
- no manual recovery required after routine disconnects or reboots

Git steps:

1. cut `release/recamera-pilot` from `main`
2. only allow stabilization fixes into this branch
3. tag the validated pilot image or commit
4. merge release fixes back to `main`

## Phase 5: Lock the Event Contract

Branch: `feature/edge-schema-contracts`

Purpose:

- prevent downstream breakage as the edge device becomes real

Work:

- define a shared detection event schema in code or documented validation rules
- validate payloads in publisher and consumer boundaries
- align edge, speed, and violation services on required fields
- add tests for malformed or partial events

Files likely affected:

- `src/edge_vision/publisher.py`
- `src/speed_estimation/main.py`
- `src/violation_detection/main.py`
- `src/data_streaming/mqtt_forwarder.py`
- tests under `tests/`

Acceptance criteria:

- downstream consumers reject bad payloads predictably
- schema changes require explicit PR review and tests

## Phase 6: One-Command Pipeline Bring-Up

Branch: `feature/pipeline-orchestration`

Purpose:

- make local and staging integration reproducible

Work:

- refactor `run_pipeline.sh` to support edge-disabled and edge-external modes
- let the pipeline run against a real remote edge device publishing into the broker
- add service dependency checks and failure handling
- document startup order and required environment variables

Acceptance criteria:

- backend-side stack starts reliably without local video assumptions
- integration test path can consume events from the reCamera

## Phase 7: Speed Estimation Calibration Workflow

Branch: `feature/speed-calibration-workflow`

Purpose:

- make speed results trustworthy after edge detection is live

Work:

- replace fixed `pixels_per_meter` assumptions with per-camera calibration data
- define calibration storage format by camera ID
- add a repeatable calibration procedure and validation script
- evaluate error against a labeled reference set

Files likely affected:

- `src/speed_estimation/calibration.py`
- `src/speed_estimation/speed_calc.py`
- `src/speed_estimation/main.py`
- `config/cameras.yaml`

Acceptance criteria:

- each deployed camera has explicit calibration data
- error bounds are documented and reproducible

## Phase 8: Backend and Data Path Hardening

Branch: `feature/backend-hardening`

Purpose:

- support multiple deployed devices cleanly

Work:

- finalize API models for detections, speeds, and violations
- add query filters by camera and time range
- add authentication for write paths if backend receives external traffic
- ensure idempotent or deduplicated event ingestion where needed

Files likely affected:

- `src/backend_api/main.py`
- `src/backend_api/models.py`
- `src/backend_api/schemas.py`
- `src/backend_api/database.py`

Acceptance criteria:

- backend supports at least one pilot edge device plus simulated load
- event ingestion and querying are stable under sustained traffic

## Phase 9: Observability and Operations

Branch: `feature/observability-healthchecks`

Purpose:

- make the system supportable after pilot deployment

Work:

- add health endpoints or heartbeat topics
- add structured logs across services
- capture FPS, inference latency, publish latency, reconnect count, and dropped event count
- document log collection and incident triage

Acceptance criteria:

- operators can identify whether failures are camera, inference, MQTT, or backend related

## Suggested Execution Order

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6
8. Phase 7
9. Phase 8
10. Phase 9

Do not start Phases 5 through 9 until Phase 4 proves that the reCamera deployment path is operational.

## What Not To Do First

Avoid these until the edge path is stable:

- deploying backend, speed estimation, and violation detection on the reCamera itself
- optimizing dashboard work before the device publishes stable events
- introducing multiple camera classes or advanced violation logic before the event contract is fixed
- trying to solve production infra and field calibration in the same PR

## Immediate Next Branch

Start with `feature/recamera-runtime-audit`.

That branch should answer one question only:

Can this repo's current edge stack run acceptably on the reCamera, or do we need to swap the inference backend while preserving the MQTT contract?