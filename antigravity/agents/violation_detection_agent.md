# Violation Detection Agent

## Role

Responsible for detecting safety violations using detection, speed, and trajectory events.

---

## Objective

Detect:

- Helmet violations
- Speed violations
- Zebra crossing violations

---

## Input

- Detection events
- Speed events
- Trajectory events

---

## Processing Pipeline


Events Ingestion
↓
Violation Rules Evaluation
↓
Generate Violation Event
↓
Publish to MQTT


---

## Violation Rules

- Helmet: motorcycle AND helmet_status == no_helmet
- Speed: speed_kmh > speed_limit
- Zebra crossing: pedestrian in crossing AND vehicle does not yield

---

## Output Event Format

```json
{
  "violation_type": "helmet_violation",
  "object_id": 123,
  "camera_id": "edge_cam_01",
  "timestamp": "ISO8601"
}
Technologies

Python

FastAPI

PostgreSQL

NumPy

Responsibilities

Rule engine implementation

Violation event generator

Violation logging

Output Deliverables

Violation detection service

Rule configuration system

Documentation for downstream analytics


