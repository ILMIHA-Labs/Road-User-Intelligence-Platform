This directory contains deployment assets for the MVP.

Files:
- `env/edge-vision.env.example`: environment variables for each reCamera device
- `env/server-common.env.example`: shared environment variables for the central server
- `systemd/*.service`: service unit templates for edge and server components

Recommended model:
- each reCamera runs only the edge vision producer
- one central server runs MQTT, backend, forwarder, speed estimation, violation detection, and dashboard

Privacy-sensitive defaults for the public release:
- `EVIDENCE_CAPTURE_ENABLED=false`
- preview and evidence retention are configurable via environment variables
