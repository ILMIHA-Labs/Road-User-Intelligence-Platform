# Demo Guide

This is the fastest reliable way to show the MVP.

## Goal

Demonstrate a working zebra-crossing safety and traffic-analytics flow using the bundled sample video.

## Recommended Demo Surface

Always use the backend-served dashboard:

- [http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/)

Do not present the raw file copy at:

- [src/dashboard/app/index.html](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/src/dashboard/app/index.html)

The `file://` copy does not represent the real live application surface.

## Demo Startup

From the repo root:

```bash
cd /Users/a2.0/Desktop/Road-User-Intelligence-Platform
bash run_pipeline.sh
```

This starts:
- MQTT broker
- backend API
- MQTT forwarder
- speed estimation
- safety-event detection
- edge vision on `data/sample.mp4`

## Demo Story

Use this narrative:

1. The sample video is ingested as a camera feed.
2. The system detects and classifies road users.
3. It counts directional flow across configured counting lines.
4. It estimates speed from tracked motion.
5. It raises safety events around zebra-crossing and stop-line behavior.
6. It stores evidence and shows the results live in the dashboard.

If you are onboarding a new camera or a new video before the demo, use the `Setup` page in the dashboard first to draw counting lines and zebra-crossing bounds directly on a preview frame.

## What To Point Out

On `Overview`:
- total detections
- total speeds
- total safety events
- total crossings
- detection class breakdown
- directional flow
- class contribution to crossings
- top counting lines

On `Cameras`:
- active camera cards
- health and snapshot freshness

On camera detail:
- live snapshot
- class breakdown
- recent detections
- recent safety events
- recent crossings
- evidence links

On `Safety Events`:
- grouped event types
- zone-based vs behavioral events
- evidence-backed records

On `Configs`:
- effective runtime camera settings
- configured zones
- configured counting lines

## Demo Success Criteria

The demo is successful if:
- the dashboard updates without manual refresh
- class counts are visible
- crossings and directional flow are visible
- at least some safety events appear
- camera detail explains what happened

## Known Demo Constraints

- Counts and event quality depend on the current sample-video framing and thresholds.
- Live previews are snapshot-based in this MVP.
- The platform is broader than zebra crossings, but the current demo intentionally emphasizes crossing safety because that is the primary operational use case.
