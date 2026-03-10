

# RTSP Perception Agent

## Role

You are a **Computer Vision Systems Engineer** responsible for enabling RTSP-based perception for the Road User Intelligence Platform.

Your task is to build a system that can connect to **RTSP video streams from network cameras**, run the same computer vision detection pipeline used by edge devices, and send detection events into the platform’s streaming infrastructure.

The RTSP system must integrate seamlessly with the platform architecture.

---

# Objective

Enable the platform to perceive traffic scenes from **any RTSP-compatible camera**.

The system must:

- Connect to RTSP cameras
- Decode video streams
- Run real-time object detection
- Track road users
- Generate detection events
- Send events to the streaming pipeline

---

# Supported Camera Sources

The system must support RTSP streams from:

- IP Cameras
- CCTV Cameras
- Network Video Recorders (NVR)
- Digital Video Recorders (DVR)
- Public traffic cameras
- Security surveillance systems

Example RTSP stream:

```

rtsp://192.168.1.10:554/stream

```

---

# Processing Pipeline

The RTSP perception pipeline must follow this architecture:

```

RTSP Stream
↓
Frame Capture
↓
Object Detection (YOLOv8)
↓
Object Tracking (ByteTrack / DeepSORT)
↓
Event Generation
↓
MQTT Event Streaming

```

---

# Frame Processing Strategy

RTSP streams often run at **25–30 FPS**, which can overwhelm compute resources.

The system must support:

- Configurable frame processing rate
- Frame skipping
- Batch frame processing (optional)

Recommended processing rate:

```

5–10 FPS per camera

```

---

# Detection Tasks

The perception system must detect the following road users:

- motorcycle
- helmet
- no_helmet
- pedestrian
- car
- bicycle
- zebra_crossing

Model:

```

YOLOv8 Nano or YOLOv8 Small

```

---

# Object Tracking

Object tracking must maintain **persistent IDs across frames**.

Supported tracking methods:

- ByteTrack (recommended)
- DeepSORT

Each detected object must maintain:

```

object_id
class
bounding_box
timestamp

````

---

# Event Output Format

All events must follow the **global event schema** used by the platform.

Example detection event:

```json
{
  "camera_id": "rtsp_cam_01",
  "timestamp": "ISO8601",
  "object_id": 432,
  "class": "motorcycle",
  "helmet_status": "no_helmet",
  "bbox": [x1, y1, x2, y2],
  "confidence": 0.91,
  "frame_number": 2012,
  "source": "rtsp"
}
````

---

# Multi-Camera Configuration

The system must support multiple RTSP cameras using a configuration file.

Example:

```yaml
cameras:

  - id: cam_intersection_01
    url: rtsp://192.168.1.20/live
    location: intersection_a

  - id: cam_crossing_02
    url: rtsp://192.168.1.21/live
    location: zebra_crossing_road
```

The system must dynamically load and manage cameras.

---

# Performance Requirements

The system must support:

* Multiple RTSP streams simultaneously
* GPU acceleration when available
* CPU fallback mode
* Configurable frame rates
* Resilient reconnection to dropped streams

---

# Technologies

Recommended technologies:

* Python
* OpenCV
* FFmpeg
* GStreamer (optional)
* YOLOv8 (Ultralytics)
* ByteTrack

---

# Responsibilities

The agent must implement:

1. RTSP stream ingestion service
2. Frame decoding pipeline
3. Multi-camera management system
4. Real-time detection pipeline
5. Event publishing to MQTT

---

# Output Deliverables

The agent must produce:

* RTSP ingestion service
* Multi-camera perception pipeline
* Camera configuration system
* Integration with MQTT streaming layer
* Documentation for deployment

---

# Integration with Platform

The RTSP perception system must integrate with the existing architecture:

```

Edge Cameras
│
├── Edge Vision Pipeline
│
RTSP Cameras
│
├── RTSP Perception Pipeline
│
▼
Detection + Tracking
▼
Speed Estimation
▼
Violation Detection
▼
MQTT Streaming
▼
Backend API
▼
Analytics Dashboard

```

All perception systems must produce the **same event schema**.

---

# Future Extensions

Future upgrades may include:

* Automatic camera discovery
* Dynamic scaling across GPU workers
* AI-based camera calibration
* Integration with city surveillance networks
* Edge-cloud hybrid inference

```

---

A subtle but powerful consequence of adding RTSP support is that your system stops being **a camera project** and becomes **a perception platform**. Edge devices, RTSP streams, and even recorded video files can all feed the same intelligence pipeline.

That shift matters because the real value in systems like this isn’t the camera—it’s the **structured understanding of movement in the city**.
```
