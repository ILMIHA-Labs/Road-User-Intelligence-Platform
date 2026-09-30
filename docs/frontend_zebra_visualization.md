# Zebra-Crossing Data — Frontend Visualization Guide

A guide for building visualizations of the zebra-crossing pipeline output. It
describes **where the data lives**, the **exact response shapes**, and
**recommended chart types** for each dataset. Everything here reflects the
current API and analysis output; field names are copied verbatim from the
backend so you can rely on them.

---

## 1. The two data planes

Zebra-crossing data comes from two independent sources. Use the right one for
the view you're building.

| Plane | What it is | Best for | Source |
|-------|-----------|----------|--------|
| **Live API** (DB-backed) | Rolling counts of detections, crossings, speeds, violations across live cameras | Dashboards, "what's happening now", time-range aggregates | REST endpoints under `/api/v1` |
| **Video-analysis job** (offline) | A researcher uploads a clip; the pipeline produces per-zone zebra events, occupancy time-series, and pedestrian-safety measures | Deep zebra-crossing analysis, per-interaction detail, annotated playback | Job artifacts: `summary.json` + CSVs |

> **Important:** the richest zebra-specific data (yielding, post-encroachment
> time, per-zone interaction events, occupancy over time) is produced by the
> **video-analysis job**, not the live API. The live API is primarily traffic
> counts/crossings/speeds. Plan your zebra screens around the job artifacts.

**Base URL:** all endpoints are served under `/api/v1` (e.g.
`GET /api/v1/live/dashboard`). Timestamps are ISO-8601 UTC. Coordinates
(zone polygons, bounding boxes) are **pixels in the camera frame**.

---

## 2. Core zebra data model

### 2.1 Zebra zone (polygon geometry)

A zone is a polygon drawn over the crossing. It appears in camera setup, in the
job `setup`, and in `summary.json.zebra_zones`.

```json
{
  "id": "zebra_north",
  "label": "North Crossing",
  "category": "zebra_crossing",
  "points": [[420, 300], [680, 300], [680, 460], [420, 460]]
}
```

- `points` — list of `[x, y]` pixel vertices (≥3), in the frame's coordinate
  space. Draw as a closed polygon overlay on the preview/snapshot image.
- Multiple zones per camera are supported; always key everything by `zone_id`.

### 2.2 Zebra interaction event types

Two event types are emitted per frame when a vehicle interacts with a zone that
has an active pedestrian:

| `event_type` | Meaning | Suggested colour |
|--------------|---------|------------------|
| `zebra_crossing_violation` | Vehicle is **inside** the crossing polygon while a pedestrian is present — a direct conflict | red |
| `zebra_yielding_risk` | Vehicle is **approaching** (near, above speed threshold) while a pedestrian is present — a risk, not yet a violation | amber |

### 2.3 Pedestrian-safety measures (derived)

The pipeline derives three research-grade safety measures per job:

- **Pedestrian episodes** — a pedestrian's wait→cross lifecycle. `outcome` is
  `crossed` or `lost`. Carries `wait_seconds`, `crossing_seconds`.
- **Yielding events** — did an approaching vehicle yield to a waiting
  pedestrian? `outcome` ∈ `yielded` / `did_not_yield` / `unresolved`.
- **Post-encroachment time (PET)** — seconds between one road user leaving a
  shared point and the next entering it. `critical: true` when below the
  threshold (default 3s).

---

## 3. Video-analysis job: lifecycle & artifacts

This is the primary flow for zebra visualization.

### 3.1 Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/video-analysis/uploads` | Upload a clip, define counting lines + `zebra_zones` |
| `GET` | `/video-analysis/jobs` | List jobs |
| `GET` | `/video-analysis/jobs/{job_id}` | Job status + `result_summary` + artifact URLs |
| `GET` | `/video-analysis/jobs/{job_id}/preview` | Still preview frame (JPEG) for drawing zone overlays |
| `POST` | `/video-analysis/jobs/{job_id}/run` | Start processing (async, `202`) |
| `GET` | `/video-analysis/jobs/{job_id}/artifacts/{artifact_name}` | Download an artifact (see names below) |
| `DELETE` | `/video-analysis/jobs/{job_id}` | Delete a job |

### 3.2 Job object

```json
{
  "job_id": "…",
  "label": "Main St crossing – morning",
  "camera_id": "cam_01",
  "status": "completed",
  "processed_frames": 5400,
  "total_frames": 5400,
  "progress_percent": 100.0,
  "failure_message": null,
  "setup": { "zebra_zones": [ … ], "zebra_speed_threshold_kmh": 15.0 },
  "preview_width": 1920,
  "preview_height": 1080,
  "preview_url": "/video-analysis/jobs/{job_id}/preview",
  "artifacts": { "annotated_video": "/video-analysis/jobs/{job_id}/artifacts/annotated_video", … },
  "result_summary": { … same shape as summary.json … },
  "created_at": "…", "started_at": "…", "completed_at": "…"
}
```

- **`status`** lifecycle: `queued` → `running` → `completed` | `failed`
  (also `deleted`, `expired` → treat as gone; API returns `410`).
- **Poll** `GET /jobs/{job_id}` while `running`; drive a progress bar from
  `progress_percent` (and `processed_frames`/`total_frames`).
- **`artifacts`** is a map of artifact name → download URL. It is populated
  only when `status === "completed"`, and only includes files that exist —
  zebra artifacts are omitted when the job has no zebra zones. Always
  feature-detect by checking for the key rather than assuming.
- `preview_width` / `preview_height` are the reference dimensions for the
  preview image — **scale zone polygons and boxes to your rendered `<img>`
  size using these**.

### 3.3 Artifact names

`annotated_video` (mp4), `summary_json`, `metrics_json`, `crossings_csv`,
`zebra_events_csv`, `zebra_occupancy_csv`, `tracks_csv`,
`pedestrian_episodes_csv`, `yielding_events_csv`, `pet_events_csv`.

> **Privacy:** the `annotated_video` has faces and licence plates blurred by
> default (redaction is on). You can embed it directly. See §7.

---

## 4. `summary.json` — the main visualization payload

Identical to the job's `result_summary`. Top-level keys:

```json
{
  "mode": "traffic_metrics",
  "camera_id": "cam_01",
  "video": { "fps": 30.0, "width": 1920, "height": 1080,
             "frame_count": 5400, "processed_frames": 5400, "duration_seconds": 180.0 },
  "calibration": { "pixels_per_meter": 12.4, "source": "pixels_per_meter" },
  "counting_lines": [ … ],
  "zebra_zones": [ { "id": "zebra_north", "label": "…", "points": [ … ] } ],
  "metrics": { … see 4.1 … },
  "zebra_metrics": { … see 4.2 … },
  "objects": [ { "object_id": 42, "class": "car", "frames_seen": 120,
                 "max_speed_kmh": 38.4, "avg_speed_kmh": 22.1 } ],
  "outputs": { "annotated_video": "…", … }
}
```

### 4.1 `metrics` (crossings, speeds, safety)

```json
{
  "total_crossings": 214,
  "counts_by_class": { "car": 180, "pedestrian": 20, "motorcycle": 14 },
  "counts_by_line": { "line_1": 214 },
  "counts_by_direction": { "a_to_b": 120, "b_to_a": 94 },
  "flow_rate_per_minute": 71.3,
  "speed_limit_kmh": 30.0,
  "speed_metrics_by_class": {
    "car": { "avg_speed_kmh": 24.1, "p85_speed_kmh": 33.0,
             "max_speed_kmh": 41.0, "compliance_rate": 0.82, "samples": 180 }
  },
  "crossing_safety": {
    "pedestrian_episodes": {
      "count": 20, "completed": 18,
      "avg_wait_seconds": 4.2, "median_wait_seconds": 3.1, "p85_wait_seconds": 8.0,
      "avg_crossing_seconds": 6.5, "median_crossing_seconds": 6.0
    },
    "yielding": {
      "opportunities": 30, "yielded": 22, "did_not_yield": 6,
      "unresolved": 2, "yielding_rate": 0.7857
    },
    "post_encroachment": {
      "events": 12, "min_pet_seconds": 1.2, "median_pet_seconds": 3.4,
      "critical_events": 3, "critical_threshold_seconds": 3.0
    }
  }
}
```

### 4.2 `zebra_metrics` (per-zone interaction rollup)

```json
{
  "events": 48,
  "zebra_yielding_risk": 33,
  "zebra_crossing_violation": 15,
  "rider_filtered_pedestrians_count": 4,
  "by_zone": {
    "zebra_north": {
      "events": 30, "zebra_yielding_risk": 20, "zebra_crossing_violation": 10,
      "unique_objects_in_zone": 26, "max_objects_in_zone": 4,
      "max_vehicles_in_zone": 2, "max_pedestrians_in_zone": 3,
      "vehicle_approach_trends": { "decelerating": 12, "steady": 6, "accelerating": 2 }
    }
  }
}
```

---

## 5. CSV artifacts — column reference

All are standard CSV with a header row. Parse client-side (e.g. PapaParse) for
per-row/timeline views.

**`zebra_events.csv`** — one row per interaction event:
`event_type, camera_id, frame_number, elapsed_seconds, zone_id,
vehicle_object_id, vehicle_class, vehicle_speed_kmh, vehicle_distance_to_zebra_m,
pedestrian_object_id, pedestrian_speed_kmh, pedestrian_distance_to_zebra_m,
vehicle_speed_trend, approach_start_speed_kmh, approach_end_speed_kmh,
approach_delta_kmh, approach_samples, rider_filtered_pedestrians_count`

**`zebra_occupancy.csv`** — per-frame, per-zone occupancy (time-series):
`frame_number, elapsed_seconds, zone_id, objects_in_zone, vehicles_in_zone,
pedestrians_in_zone, bikes_in_zone, class_counts_json`

**`pedestrian_episodes.csv`**:
`camera_id, zone_id, pedestrian_object_id, wait_start_seconds,
crossing_start_seconds, crossing_end_seconds, wait_seconds, crossing_seconds,
outcome`

**`yielding_events.csv`**:
`camera_id, zone_id, vehicle_object_id, vehicle_class, opened_seconds,
resolved_seconds, approach_speed_kmh, min_approach_speed_kmh, outcome,
pedestrians_active`

**`pet_events.csv`**:
`camera_id, zone_id, first_object_id, first_class, second_object_id,
second_class, first_exit_seconds, second_entry_seconds, pet_seconds,
encroachment_order, second_speed_kmh, critical`

**`tracks.csv`** (per-frame per-object; drives overlays/heatmaps):
`frame_number, elapsed_seconds, camera_id, object_id, class, confidence, bbox,
speed_kmh, is_rider, associated_vehicle_id, zebra_zone_id, inside_zebra,
near_zebra, distance_to_zebra_m, inside_zebra_zone_ids, near_zebra_zone_ids`
(`bbox` is a JSON string `[x1, y1, x2, y2]` in pixels.)

**`crossings.csv`**:
`camera_id, line_id, line_label, object_id, class, direction, timestamp,
frame_number, elapsed_seconds, source`

---

## 6. Live API (dashboard plane)

Use these for real-time camera dashboards. Note: these are traffic
counts/crossings, not the rich zebra measures.

| Path | Returns |
|------|---------|
| `GET /live/dashboard` | Snapshot: `by_camera`, `crossings` (see below), camera config, `status: "live"` |
| `GET /live/cameras` | Per-camera `health` (`online` / `offline`) |
| `GET /live/cameras/{id}/snapshot` | Latest frame (for overlays) |
| `GET /analytics/crossings` | Crossing aggregates for a time range |
| `GET /analytics/summary` | Totals |

**`/analytics/crossings` (and `dashboard.crossings`) shape:**

```json
{
  "camera_id": "cam_01", "start": "…", "end": "…",
  "total_crossings": 214,
  "directions": [ { "direction": "a_to_b", "count": 120 } ],
  "classes": [ { "class": "pedestrian", "count": 20 } ],
  "lines": [ { "line_id": "line_1", "line_label": "Main", "count": 214, "directions": { … } } ],
  "counts_by_direction": { … }, "counts_by_class": { … }, "counts_by_line": { … },
  "flow_rate_per_minute": 71.3,
  "speed_metrics_by_class": { "car": { "avg_speed_kmh": 24.1, "max_speed_kmh": 41.0, "samples": 180 } }
}
```

**Exports** (server-generated files, good for "download data" buttons):
`GET /exports/safety-events.csv`, `/exports/crossings.csv`,
`/exports/traffic-flow.json`, `/exports/research-bundle.zip`.
`safety-events.csv` columns: `id, timestamp, camera_id, violation_type,
object_id, evidence_url, evidence_media_type`.

**Privacy status:** `GET /privacy/redaction` reports whether imagery redaction
and k-anonymity are active — surface this in the UI so users know stored imagery
is blurred.

---

## 7. Recommended visualizations

| Data | Chart | Notes |
|------|-------|-------|
| `zebra_metrics.by_zone` violations vs. yielding-risk | Stacked bar per zone | red = violation, amber = yielding-risk |
| `zebra_occupancy.csv` (`vehicles_in_zone`, `pedestrians_in_zone`) | Multi-series area/line over `elapsed_seconds` | one small-multiple per `zone_id`; shows conflict windows |
| `zebra_events.csv` on a timeline | Event scatter/lollipop over `elapsed_seconds`, colour by `event_type` | click a marker → seek `annotated_video` to `elapsed_seconds` |
| `crossing_safety.yielding` | Donut (`yielded` / `did_not_yield` / `unresolved`) + big `yielding_rate` KPI | |
| `pedestrian_episodes.csv` `wait_seconds` | Histogram / box plot; KPI tiles for median & p85 wait | |
| `pet_events.csv` `pet_seconds` | Histogram with a threshold line at `critical_threshold_seconds`; flag `critical` rows | low PET = dangerous |
| `speed_metrics_by_class` `compliance_rate` | Bar per class, with `speed_limit_kmh` reference | |
| Zone geometry + `tracks.csv` `inside_zebra` points | Polygon overlay on `preview_url`, optional heatmap of occupied pixels | scale by `preview_width/height` |
| `counts_by_direction` / `counts_by_class` | Bars or a small flow diagram | |

**Overlay drawing:** load `preview_url` (or a live snapshot), then draw each
zone's `points` as an SVG/Canvas polygon. Scale every coordinate by
`renderedWidth / preview_width` and `renderedHeight / preview_height`. Bounding
boxes from `tracks.csv` use the same space.

**Timeline sync:** `elapsed_seconds` is the shared clock across
`zebra_events`, `zebra_occupancy`, and the `annotated_video`. Use it to link a
chart cursor to video playback (`video.currentTime = elapsed_seconds`).

---

## 8. Practical notes

- **Feature-detect zebra data.** A job/camera without zebra zones has no zebra
  artifacts and no `zebra_metrics`. Check for the artifact key / object before
  rendering a zebra panel.
- **Empty ranges.** Counts can be `0` and metric objects can be empty — render
  empty states, don't assume non-zero.
- **k-anonymity nulls.** If the operator enables k-anonymity, some aggregate
  counts in the research/analytics endpoints come back as `null` (suppressed
  small groups). Treat `null` as "hidden", not zero.
- **Polling cadence.** For a running job, poll `GET /jobs/{job_id}` every
  1–2 s; stop when `status` is `completed`/`failed`.
- **Units.** Speeds are km/h, distances metres, times seconds, coordinates
  pixels.
