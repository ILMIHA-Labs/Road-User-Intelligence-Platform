# Standards and Best Practices Compliance

This document supports the current DPG indicator on **Open Standards and Best
Practices** by describing the main technical standards used in the repository.

## MQTT messaging

- Standard: MQTT publish/subscribe messaging
- Usage: perception, speed, crossing, and safety-event transport
- Implementation references:
  - `src/edge_vision/publisher.py`
  - `src/speed_estimation/main.py`
  - `src/violation_detection/main.py`
  - `src/data_streaming/mqtt_forwarder.py`

## HTTP APIs and OpenAPI

- Standard: FastAPI-generated OpenAPI schemas
- Usage: ingestion, analytics, exports, and dashboard data access
- Implementation references:
  - `src/backend_api/main.py`
  - `src/backend_api/schemas.py`

## Data interchange

- Standard: JSON payloads over MQTT and HTTP
- Usage: detections, speeds, crossings, safety events, and dashboard state
- Implementation references:
  - `src/data_streaming/mqtt_forwarder.py`
  - `src/backend_api/schemas.py`
  - `src/common/event_schemas.py`

## Configuration and portability

- Standard: plain-text YAML configuration
- Usage: authoritative runtime camera configuration in `config/cameras.yaml`
- Portability stance:
  - `reCamera` is optional
  - webcam, RTSP, and file inputs remain supported

## Software engineering best practices in the public release

- reproducible Python environment via `requirements.txt`,
  `requirements-dev.txt`, and `pyproject.toml`
- automated test run in CI
- repository hygiene checks for tracked runtime junk
- governance and security policy files published at the repository root

## Related governance references

- `docs/dpg_readiness.md`
- `PRIVACY_POLICY.md`
- `SECURITY.md`
- `docs/data_governance.md`
