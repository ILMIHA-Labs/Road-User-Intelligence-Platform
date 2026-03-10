# Backend API Agent

## Role

Responsible for central API and data storage of the platform.

---

## Objective

- Provide REST endpoints for all event types
- Support storage in PostgreSQL
- Integrate with MQTT streaming

---

## Input

- Detection, speed, trajectory, violation events from streaming agent

---

## Core Endpoints

- POST /detections
- POST /speeds
- POST /violations
- POST /trajectories
- GET /analytics
- GET /devices

---

## Database Schema

Tables:

- devices
- detections
- speeds
- violations
- trajectories

All tables must include timestamps and indexes.

---

## Technologies

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- Redis
- Celery

---

## Responsibilities

- API implementation
- Data ingestion
- Authentication
- Event validation
- Scalable backend architecture

---

## Output Deliverables

- Fully functional API service
- Database schema scripts
- Integration with streaming agent
- Documentation