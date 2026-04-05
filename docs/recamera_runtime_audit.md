# ReCamera Phase 0 Runtime Audit

## Scope

This document operationalizes Phase 0 from docs/recamera_deployment_plan.md for branch feature/recamera-runtime-audit.

## Outcome Required

Make one explicit decision:

- Path A: Keep Python plus Ultralytics on device
- Path B: Use native reCamera inference runtime and keep MQTT payload contract unchanged

## On-Device Prerequisites

1. Device is upgraded to latest stable reCamera OS.
2. SSH access works.
3. Device has network route to the MQTT broker host and port.
4. You know the camera source index or RTSP/source URI you will run in production.

## Artifacts to Produce in This Branch

1. Runtime metrics report at docs/recamera_runtime_audit_results.md
2. Raw probe outputs under artifacts/recamera_phase0/
3. Final recommendation section appended to docs/recamera_runtime_audit_results.md

## Execution Checklist

### 1. Baseline System Probe

Run on device:

bash scripts/recamera/runtime_probe.sh --broker-host <BROKER_HOST> --broker-port 1883 --out-dir artifacts/recamera_phase0

Expected:

- system info file generated
- network reachability checks logged
- Python and package import checks logged

### 2. Capture and Inference Smoke

Run on device:

PYTHONPATH=$PWD/src python src/edge_vision/main.py --source 0 --camera-id recamera_01 --broker <BROKER_HOST> --port 1883

Expected:

- no immediate crash
- detection loop starts
- publish attempts visible in logs

### 3. Stability Window

Run for a fixed window (minimum 30 minutes, target 2 hours).

Record:

- average FPS
- peak memory
- CPU utilization trend
- thermal trend (if available)
- publish success and reconnect behavior

### 4. Decision Gate

If all are true, choose Path A:

- acceptable sustained FPS for use case
- stable memory and temperature
- reliable publishes to broker
- dependency installation is reproducible

Else choose Path B and list required refactor scope to adapt native inference output to current MQTT schema.

## Result Template

Create docs/recamera_runtime_audit_results.md with:

1. Device model and OS version
2. Python version and package install method
3. Probe output summary table
4. Stability run metrics
5. Decision: Path A or Path B
6. Risks and mitigation
7. Next branch recommendation

## Git Steps for This Phase

1. git checkout main
2. git pull --ff-only
3. git checkout -b feature/recamera-runtime-audit
4. Commit audit scripts and templates
5. Commit collected artifacts separately
6. Open PR with decision and evidence
