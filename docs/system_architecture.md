# Road User Intelligence Platform – System Architecture

This diagram shows the full architecture of the Road User Intelligence Platform MVP, including:

- Edge cameras
- RTSP camera ingestion
- Traffic simulation
- Detection & tracking
- Speed estimation
- Violation detection
- Trajectory prediction
- MQTT streaming
- Backend storage
- Analytics dashboard

---

## Full System Architecture

```mermaid
flowchart TD

%% INPUT SOURCES
A[Edge Cameras\nJetson / Edge Devices]
B[RTSP Cameras\nIP Cameras / CCTV]
C[Traffic Simulation Agent\nSynthetic Scenes]

%% PERCEPTION
D[Edge Vision Agent\nDetection + Tracking]
E[RTSP Perception Agent\nDetection + Tracking]

%% UNIFIED EVENTS
F[Detection Events\nUnified Schema]

%% MOTION ANALYSIS
G[Speed Estimation Agent]

%% BEHAVIOR ANALYSIS
H[Violation Detection Agent\nHelmet / Speed / Zebra]

%% PREDICTION
I[Trajectory Prediction Agent]

%% STREAMING
J[MQTT Broker\nEvent Bus]

%% BACKEND
K[Backend API\nFastAPI]

%% DATABASE
L[(PostgreSQL\nTraffic Data)]

%% DATA PIPELINES
M[Data Engineering Agent\nETL + Aggregations]

%% ANALYTICS
N[Analytics Dashboard\nGrafana / Superset]

%% RESEARCH
O[Research & Evaluation Agent\nMetrics + Experiments]

%% FLOW
A --> D
B --> E
C --> F

D --> F
E --> F

F --> G
G --> H
H --> I

I --> J
H --> J
G --> J
F --> J

J --> K

K --> L

L --> M
M --> N

L --> O
````

---

# Event Streaming Topics

All modules communicate via **MQTT**.

| Topic                 | Producer                            | Consumer                     |
| --------------------- | ----------------------------------- | ---------------------------- |
| `camera/detections`   | Edge Vision, RTSP Agent, Simulation | Speed Estimation, Backend    |
| `camera/speeds`       | Speed Estimation Agent              | Violation Detection, Backend |
| `camera/violations`   | Violation Detection Agent           | Backend, Dashboard           |
| `camera/trajectories` | Trajectory Prediction               | Backend, Dashboard           |

---

# Data Pipeline Overview

```
Cameras / Simulation
        ↓
Detection + Tracking
        ↓
Speed Estimation
        ↓
Violation Detection
        ↓
Trajectory Prediction
        ↓
MQTT Event Streaming
        ↓
Backend API
        ↓
PostgreSQL Database
        ↓
Data Engineering
        ↓
Analytics Dashboard
```

---

# Deployment Layout

Example deployment for MVP:

```
Edge Device
 ├── Edge Vision Agent

Server / GPU Node
 ├── RTSP Perception Agent
 ├── Speed Estimation Agent
 ├── Violation Detection Agent
 ├── Trajectory Prediction Agent

Cloud / Backend
 ├── MQTT Broker
 ├── FastAPI Backend
 ├── PostgreSQL Database
 ├── Data Engineering Pipelines
 └── Analytics Dashboard
```

---

# MVP Camera Capacity

Initial MVP target:

| Component     | Capacity |
| ------------- | -------- |
| Edge Cameras  | 5        |
| RTSP Cameras  | 5        |
| Total Streams | 10       |

Future scaling goal:

```
100+ cameras
multi-GPU inference
distributed processing
```

---

# Simulation Integration

Traffic Simulation Agent can inject events into the same pipeline.

This enables:

* rare event testing
* algorithm benchmarking
* synthetic dataset generation
* stress testing analytics

Simulation publishes to:

```
camera/detections
camera/trajectories
```

---

# Key Design Principle

All modules communicate using a **shared event schema**.

This allows:

* plug-and-play agents
* independent development
* scalable architecture
* easy debugging

```

---

