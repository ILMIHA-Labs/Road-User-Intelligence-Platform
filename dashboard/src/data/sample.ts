import { fromSummaryFile } from "./adapters";
import type { AnalysisSummary } from "./types";

/**
 * A realistic sample job for prototyping the views without a live API.
 * Shape conforms exactly to AnalysisSummary (the backend summary.json).
 */
export const SAMPLE_SUMMARY: AnalysisSummary = {
  mode: "traffic_metrics",
  camera_id: "cam-oxford-st",
  video: {
    path: "oxford_st_0830.mp4",
    fps: 25,
    width: 1920,
    height: 1080,
    frame_count: 13500,
    processed_frames: 13500,
    duration_seconds: 540,
  },
  calibration: { source: "reference_distance", pixels_per_meter: 22.4 },
  counting_lines: [{ id: "line-nb", label: "Northbound" }, { id: "line-sb", label: "Southbound" }],
  zebra_zones: [{ id: "zebra-main" }],
  metrics: {
    total_crossings: 428,
    counts_by_class: { car: 243, bus: 18, truck: 31, motorcycle: 46, bicycle: 38, pedestrian: 52 },
    counts_by_line: { "line-nb": 221, "line-sb": 207 },
    counts_by_direction: { northbound: 221, southbound: 207 },
    flow_rate_per_minute: 47.6,
    speed_limit_kmh: 30,
    speed_metrics_by_class: {
      car: { avg_speed_kmh: 27.4, max_speed_kmh: 52.1, p85_speed_kmh: 34.8, samples: 243, compliance_rate: 0.78 },
      bus: { avg_speed_kmh: 22.1, max_speed_kmh: 31.5, p85_speed_kmh: 28.0, samples: 18, compliance_rate: 0.94 },
      truck: { avg_speed_kmh: 24.6, max_speed_kmh: 39.2, p85_speed_kmh: 31.1, samples: 31, compliance_rate: 0.87 },
      motorcycle: { avg_speed_kmh: 31.8, max_speed_kmh: 61.4, p85_speed_kmh: 44.2, samples: 46, compliance_rate: 0.61 },
    },
    crossing_safety: {
      pedestrian_episodes: {
        count: 64,
        completed: 58,
        avg_wait_seconds: 6.8,
        median_wait_seconds: 5.2,
        p85_wait_seconds: 14.1,
        avg_crossing_seconds: 7.9,
        median_crossing_seconds: 7.4,
      },
      yielding: { opportunities: 73, yielded: 49, did_not_yield: 18, unresolved: 6, yielding_rate: 0.7313 },
      post_encroachment: {
        events: 21,
        min_pet_seconds: 0.8,
        median_pet_seconds: 3.4,
        critical_events: 5,
        critical_threshold_seconds: 2.0,
      },
    },
  },
  zebra_metrics: {
    events: 39,
    zebra_yielding_risk: 24,
    zebra_crossing_violation: 15,
    rider_filtered_pedestrians_count: 7,
    by_zone: {
      "zebra-main": {
        events: 39,
        zebra_yielding_risk: 24,
        zebra_crossing_violation: 15,
        unique_objects_in_zone: 112,
        max_objects_in_zone: 6,
        max_vehicles_in_zone: 3,
        max_pedestrians_in_zone: 4,
        vehicle_approach_trends: { decelerating: 44, steady: 19, accelerating: 10 },
      },
    },
  },
  objects: [
    { object_id: 1, class: "car", frames_seen: 142, max_speed_kmh: 41.2, avg_speed_kmh: 28.9 },
    { object_id: 2, class: "pedestrian", frames_seen: 88, max_speed_kmh: 6.1, avg_speed_kmh: 4.3 },
    { object_id: 3, class: "motorcycle", frames_seen: 61, max_speed_kmh: 58.7, avg_speed_kmh: 36.5 },
    { object_id: 4, class: "bus", frames_seen: 203, max_speed_kmh: 29.8, avg_speed_kmh: 19.2 },
  ],
  outputs: {},
};

export const SAMPLE_JOB = fromSummaryFile(SAMPLE_SUMMARY, {
  jobId: "sample-oxford-st",
  label: "Oxford St — 08:30 sample",
  originalFilename: "oxford_st_0830.mp4",
});
