


# Road User Intelligence Platform – Integration Guide

## Overview

This guide explains how **all agents are connected**, including **data flow, event schema, and module dependencies**, for both real and simulated traffic sources.

---

## 1. Sources of Input

### 1.1 Edge Cameras

- Run **Edge Vision Agent** on edge hardware (e.g., reCamera, Jetson Nano/Orin)
- Produces **Detection Events** in the platform schema
- Publishes events via **MQTT** to `camera/detections`

### 1.2 RTSP Cameras

- Run **RTSP Perception Agent**
- Connects to **any RTSP-compatible camera**
- Runs detection + tracking pipelines like edge devices
- Publishes events via **MQTT** to the same topics

### 1.3 Traffic Simulation

- Run **Traffic Simulation Agent**
- Generates synthetic detection and trajectory events
- Supports testing rare or dangerous traffic situations
- Publishes events via **MQTT** using the same schema
- Can simulate:
  - Speed variations
  - Zebra crossing violations
  - Multiple object interactions

---

## 2. Event Streaming

### 2.1 MQTT Topics

| Topic                     | Event Type                  | Producers                                | Consumers                               |
|----------------------------|----------------------------|-----------------------------------------|----------------------------------------|
| camera/detections          | Detection                  | Edge Vision, RTSP, Simulation           | Speed Estimation, Violation Detection, Trajectory Prediction, Backend API |
| camera/speeds              | Speed                      | Speed Estimation Agent                   | Violation Detection, Backend API, Dashboard |
| camera/violations          | Violations                 | Violation Detection Agent                | Backend API, Dashboard, Research Agent |
| camera/trajectories        | Predicted Trajectories     | Trajectory Prediction Agent, Simulation | Backend API, Dashboard, Research Agent |

---

## 3. Perception → Motion Analysis → Behavior

```

Edge Cameras ──┐
│
RTSP Cameras ──┼─> Detection + Tracking (Unified Pipeline)
│
Traffic Simulation ──┘
↓
Speed Estimation Agent
↓
Violation Detection Agent
↓
Trajectory Prediction Agent

```

**Notes:**

- All agents use **same detection schema**.
- Speed and trajectory calculations require **camera calibration**.
- Violations depend on **speed events + detection events**.

---

## 4. Data Transport & Backend

- All events are published to **MQTT broker** by source agents.
- **Data Streaming Agent** validates schemas and forwards events to backend.
- Backend API stores events in PostgreSQL:
  - Detections → `detections` table
  - Speeds → `speeds` table
  - Violations → `violations` table
  - Trajectories → `trajectories` table

```

MQTT Broker
↓
Data Streaming Agent
↓
Backend API (PostgreSQL)
↓
Data Engineering Agent → Analytics Dashboard

```

---

## 5. Analytics Dashboard

- Queries PostgreSQL/InfluxDB for:
  - Helmet compliance
  - Speed distributions
  - Zebra crossing violations
  - Traffic flow visualizations
  - Predicted trajectories

- Supports **real-time monitoring** and **historical analytics**.

---

## 6. Traffic Simulation Integration

- **Simulation Agent** can feed **any downstream agent**:
  - Detections → Speed Estimation, Violations
  - Trajectories → Prediction, Dashboard
- Enables **testing without real cameras**.

---

## 7. Trajectory Prediction

- Consumes:
  - Detection + Tracking Events
  - Speed Events
- Produces **Predicted Path Events** via MQTT
- Feeds Dashboard and Research Agent

---

## 8. Research & Evaluation

- Consumes **all events** from backend or MQTT
- Computes metrics:
  - Detection accuracy
  - Tracking consistency
  - Speed estimation error
  - Violation detection accuracy
  - Prediction trajectory error
- Generates **reports** for system validation or publications

---

## 9. Cloud & Deployment

- **Cloud Infrastructure Agent** handles:
  - Deployment of backend, MQTT broker, dashboards
  - Horizontal scaling for multiple RTSP streams
  - GPU resource management for detection agents
- Edge devices or RTSP ingestion can run on local machines or cloud GPU instances

---

## 10. Summary of Integration Flow

```

[Edge Cameras]       [RTSP Cameras]       [Simulation Agent]
│                     │                     │
└──────────┬──────────┴──────────┬──────────┘
▼
Detection + Tracking
│
Speed Estimation
│
Violation Detection
│
Trajectory Prediction
│
MQTT Event Streaming
│
Backend API
│
Data Engineering Agent
│
Analytics Dashboard
│
Research & Evaluation

```

- **Unified Event Schema** ensures interoperability.
- **Simulation Agent** allows testing before full deployment.
- **MQTT Broker** centralizes real-time streaming.
- **Backend** ensures historical data storage and analytics.

---

## 11. Development Notes

1. Start by implementing **edge + RTSP perception pipelines**.
2. Implement **speed estimation** and **violation detection**.
3. Deploy **backend API** and **data streaming**.
4. Integrate **trajectory prediction** and **simulation agent**.
5. Connect **analytics dashboard** and validate via **research & evaluation agent**.
6. Scale using **cloud infrastructure** for production.

---

This Integration Guide provides a **complete map** of how each module interacts and streams data in real-time while supporting simulation and prediction.  
