# Data Streaming Agent

## Role

Responsible for transporting events from perception modules to the backend reliably.

---

## Objective

- Stream detection, speed, violation, and trajectory events
- Support both edge and RTSP sources
- Ensure reliable delivery to backend API

---

## Input

- Detection, speed, trajectory, violation events

---

## Processing Pipeline


Event Reception
↓
Validate Event Schema
↓
Publish to MQTT Broker
↓
Optional: Log to local buffer


---

## MQTT Topics

- camera/detections
- camera/speeds
- camera/violations
- camera/trajectories

---

## Technologies

- Python
- MQTT (Mosquitto / EMQX)
- paho-mqtt

---

## Responsibilities

- Event schema validation
- MQTT broker management
- Multi-source support
- Reliable delivery and retry handling

---

## Output Deliverables

- Streaming service
- MQTT topic structure
- Documentation for integration