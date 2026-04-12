# Functional Requirements

This document defines baseline functional requirements for the Road User Intelligence Platform.

## FR-1 Camera Ingestion

- The platform shall ingest video from edge cameras and RTSP sources.
- The platform shall support per-camera identifiers.
- The platform shall support simulated events for testing.

## FR-2 Detection and Tracking

- The platform shall perform object detection and tracking on configured streams.
- The platform shall produce detection events with timestamp, object ID, class, confidence, and bounding box.
- The platform shall publish detection events to `camera/detections`.

## FR-3 Speed Estimation

- The platform shall calculate object speed from tracked detections.
- The platform shall produce speed events with camera ID, object ID, speed, and timestamp.
- The platform shall publish speed events to `camera/speeds`.

## FR-4 Violation Detection

- The platform shall evaluate configured rule logic on detection and speed events.
- The platform shall produce violation events with violation type, object ID, camera ID, and timestamp.
- The platform shall publish violation events to `camera/violations`.

## FR-5 Data Streaming and Persistence

- The platform shall subscribe to MQTT topics and forward valid events to backend APIs.
- The backend shall persist detections, speeds, violations, and trajectories in the database.
- The platform shall expose health status and basic analytics summary endpoints.

## FR-6 Configuration and Deployment

- The platform shall allow broker host/port and camera metadata configuration.
- The platform shall support local MVP pipeline execution from a single startup script.
- The platform shall support edge-plus-server deployment topology.

## FR-7 Observability

- The platform shall emit logs for startup, processing, and shutdown.
- The platform shall log event publish/forward failures.
- The platform shall support operational troubleshooting from service logs.

## FR-8 Testing

- The platform shall include unit tests for backend, data engineering, speed estimation, and violation modules.
- The platform shall support integration validation of MQTT-to-backend event flow.
