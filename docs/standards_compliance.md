# Standards and Best Practices Compliance

This document records open standards and engineering best practices used by the Road User Intelligence Platform.

## 1. MQTT Messaging Standard

- Standard: MQTT publish/subscribe messaging
- Usage: Event transport across perception, analytics, and backend services
- Topics:
  - `camera/detections`
  - `camera/speeds`
  - `camera/violations`
  - `camera/trajectories`
- Implementation references:
  - `src/edge_vision/publisher.py`
  - `src/speed_estimation/main.py`
  - `src/violation_detection/main.py`
  - `src/data_streaming/mqtt_forwarder.py`
- Validation approach:
  - Pipeline smoke tests and topic subscription checks
  - End-to-end persistence verification in database tables

## 2. REST API and OpenAPI

- Standard: OpenAPI via FastAPI automatic schema generation
- Usage: Backend ingestion endpoints and analytics summary endpoint
- Implementation references:
  - `src/backend_api/main.py`
  - `src/backend_api/schemas.py`
- Validation approach:
  - HTTP `201 Created` responses for ingestion endpoints
  - Endpoint schema validation through FastAPI/Pydantic models

## 3. Data Modeling and Interchange

- Standard: JSON event payloads over MQTT and HTTP
- Usage: Unified event schema for detections, speeds, violations, trajectories
- Implementation references:
  - `src/edge_vision/publisher.py`
  - `src/data_streaming/mqtt_forwarder.py`
  - `src/backend_api/schemas.py`
- Validation approach:
  - Pydantic schema parsing in backend API
  - Forwarder JSON decode checks and error logging

## 4. Deployment and Operations Best Practices

- Practice: Service startup checks and fail-fast behavior
- Practice: Structured logs for troubleshooting
- Practice: Edge/runtime audit workflow before production rollout
- Implementation references:
  - `run_pipeline.sh`
  - `docs/recamera_deployment_plan.md`
  - `docs/recamera_runtime_audit.md`
- Validation approach:
  - Startup log checks and service health checks
  - Runtime audit evidence collection

## 5. Current Gaps and Planned Additions

- Formal API versioning and contract governance document
- Expanded integration and fault-injection test suites
- Security hardening and policy artifacts under dedicated governance docs
