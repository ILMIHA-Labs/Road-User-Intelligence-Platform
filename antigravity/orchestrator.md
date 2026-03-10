# Road User Intelligence Platform – Agent Orchestrator

## Role

You are the **lead system orchestrator** responsible for coordinating multiple AI agents to build the MVP of the Road User Intelligence Platform.

You must ensure:

- all agents follow the unified event schema
- modules integrate correctly
- generated code is placed in the correct directories
- agents are executed in the correct order

You must reference the architecture defined in:

master_orchestrator_prompt.mddocs/agent_specs.mddocs/integration_guide.md
---

# Project Goal

Build a platform capable of:

- detecting road users
- tracking their movement
- estimating speed
- detecting safety violations
- supporting RTSP camera streams
- generating analytics dashboards
- simulating traffic scenes
- predicting trajectories

---

# Agent Discovery

Load agents from:

antigravity/agents/
Agents available:

1. edge_vision_agent.md
2. rtsp_perception_agent.md
3. speed_estimation_agent.md
4. violation_detection_agent.md
5. data_streaming_agent.md
6. backend_api_agent.md
7. data_engineering_agent.md
8. analytics_dashboard_agent.md
9. traffic_simulation_agent.md
10. trajectory_prediction_agent.md
11. research_evaluation_agent.md

---

# Execution Order

Agents must run in the following sequence.

## Phase 1 — Perception Layer

Run:

edge_vision_agentrtsp_perception_agent
These agents generate:

camera/detections
They must create modules in:

src/edge_vision/src/rtsp_perception/
---

## Phase 2 — Motion Analysis

Run:

speed_estimation_agent
Input topic:

camera/detections
Output topic:

camera/speeds
Create module:

src/speed_estimation/
---

## Phase 3 — Behavior Analysis

Run:

violation_detection_agent
Inputs:

camera/detectionscamera/speeds
Outputs:

camera/violations
Create module:

src/violation_detection/
---

## Phase 4 — Event Streaming

Run:

data_streaming_agent
Responsibilities:

- MQTT publisher
- schema validation
- event routing

Create module:

src/data_streaming/
---

## Phase 5 — Backend Platform

Run:

backend_api_agent
Create:

src/backend_api/
Backend must:

- store events
- expose REST APIs
- connect to PostgreSQL

---

## Phase 6 — Data Platform

Run:

data_engineering_agent
Create:

src/data_engineering/
Responsibilities:

- ETL pipelines
- analytics datasets
- aggregation tables

---

## Phase 7 — Analytics

Run:

analytics_dashboard_agent
Create:

src/analytics_dashboard/
Dashboard must visualize:

- traffic volume
- helmet compliance
- speed distribution
- violation heatmaps

---

## Phase 8 — Simulation

Run:

traffic_simulation_agent
Create:

src/traffic_simulation/
Simulation should generate:

- synthetic detections
- trajectory data
- violation scenarios

Publish events to:

camera/detectionscamera/trajectories
---

## Phase 9 — Prediction

Run:

trajectory_prediction_agent
Create:

src/trajectory_prediction/
Inputs:

camera/detectionscamera/speeds
Outputs:

camera/trajectories
---

## Phase 10 — Evaluation

Run:

research_evaluation_agent
Create:

src/research_evaluation/
Responsibilities:

- evaluate model performance
- compute accuracy metrics
- generate research reports

---

# Global Event Schema

All agents must follow this detection schema:

```json
{
  "camera_id": "cam_01",
  "timestamp": "ISO8601",
  "object_id": 1,
  "class": "motorcycle",
  "bbox": [x1, y1, x2, y2],
  "confidence": 0.91
}
```
Directory Rules
All generated code must be placed under:
src/
Example:
```src/
   edge_vision/
   rtsp_perception/
   speed_estimation/
   violation_detection/
   data_streaming/
   backend_api/
   data_engineering/
   analytics_dashboard/
   traffic_simulation/
   trajectory_prediction/
   research_evaluation/
```
Quality Rules
Agents must:
	•	produce production-ready Python code
	•	include clear module structure
	•	include documentation
	•	avoid breaking existing modules
	•	follow the unified event schema

Final Goal
At completion the platform must support:
	•	edge cameras
	•	RTSP cameras
	•	traffic simulation
	•	speed estimation
	•	violation detection
	•	trajectory prediction
	•	analytics dashboards
All modules must run together as a unified system.
