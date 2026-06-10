# Demo Guide

This guide describes the recommended public-demo path for the
research-reference MVP.

## Goal

Demonstrate a working zebra-crossing safety and traffic-analytics flow using a
licensed local video source or a live camera source under the operator’s
control.

This is the canonical public evaluation workflow for outside researchers.

## Recommended demo surface

Always use the backend-served dashboard and the exact URL printed by the
startup script.

Do not present the raw file copy at:

- `src/dashboard/app/index.html`

The `file://` copy does not represent the real live application surface.

## Demo startup

From the repo root:

```bash
cd Road-User-Intelligence-Platform
export DEMO_VIDEO_SOURCE=/absolute/path/to/your/video.mp4
bash run_pipeline.sh
```

This starts:

- MQTT broker
- backend API
- MQTT forwarder
- speed estimation
- safety-event detection
- edge vision on the licensed source you supplied

## Demo story

Use this narrative:

1. The selected video is ingested as a camera feed.
2. The system detects and classifies road users.
3. It counts directional flow across configured counting lines.
4. It estimates speed from tracked motion.
5. It raises safety events around zebra-crossing and stop-line behavior.
6. It shows the results live in the dashboard and, if explicitly enabled,
   evidence-backed review context.

If you are onboarding a new camera or a new video before the demo, use the
`Setup` page in the dashboard first to draw counting lines and zebra-crossing
bounds directly on a preview frame.

If you want a standalone report from a licensed prerecorded clip without
feeding it into live monitoring, use the `Video Analysis` page instead. Upload
the clip, draw session-local counting lines, and optionally add zebra polygons
for crossing-safety analysis before downloading the annotated-video and report
artifacts. These temporary results do not enter the operational event database
and expire after 24 hours by default.

For a release-ready run, also verify the checklist in `docs/release_checklist.md`.

## What to point out

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
- evidence links, when evidence capture has been enabled

On `Safety Events`:

- grouped event types
- zone-based vs behavioral events
- evidence-backed records, when evidence capture has been enabled

On `Configs`:

- effective runtime camera settings
- configured zones
- configured counting lines

## Known demo constraints

- The public repository does not assume a bundled redistributable demo video.
- Counts and event quality depend on scene geometry and thresholds.
- Live previews are snapshot-based in this MVP.
- The platform is broader than zebra crossings, but the current demo
  intentionally emphasizes crossing safety.
