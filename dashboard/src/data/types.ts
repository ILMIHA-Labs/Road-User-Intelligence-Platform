/**
 * Normalized data model for the analytics dashboard.
 *
 * Design: the analytics payload types below mirror the backend JSON shape
 * (snake_case, 1:1 with `summary.json` / the job `result_summary`). The two
 * data sources — the live API and imported export files — produce the SAME
 * `AnalysisSummary`, so adapters validate and wrap rather than rename fields.
 * The `DashboardJob` envelope normalizes only what actually differs between
 * sources: where the data came from, and how an artifact (video, CSV) is
 * reached. See wayfinder ticket #14.
 */

// ---------------------------------------------------------------------------
// Artifact names (exactly the backend's _VIDEO_ANALYSIS_ARTIFACTS keys)
// ---------------------------------------------------------------------------

export const ARTIFACT_NAMES = [
  "annotated_video",
  "summary_json",
  "metrics_json",
  "crossings_csv",
  "zebra_events_csv",
  "zebra_occupancy_csv",
  "tracks_csv",
  "pedestrian_episodes_csv",
  "yielding_events_csv",
  "pet_events_csv",
] as const;

export type ArtifactName = (typeof ARTIFACT_NAMES)[number];

/** Artifacts that only exist when a zebra-crossing layer was configured. */
export const ZEBRA_ARTIFACT_NAMES: ReadonlySet<ArtifactName> = new Set([
  "zebra_events_csv",
  "zebra_occupancy_csv",
  "pedestrian_episodes_csv",
  "yielding_events_csv",
  "pet_events_csv",
]);

// ---------------------------------------------------------------------------
// Analysis summary (= summary.json = job.result_summary)
// ---------------------------------------------------------------------------

export interface VideoMeta {
  path: string;
  fps: number;
  width: number;
  height: number;
  frame_count: number;
  processed_frames: number;
  duration_seconds: number;
}

/**
 * Calibration is tolerant of both shapes the backend may emit:
 * the scalar `{ pixels_per_meter, source }` and the richer `describe()`
 * output from the accuracy work (homography / reference distance).
 */
export interface Calibration {
  source: string;
  pixels_per_meter?: number | null;
  [key: string]: unknown;
}

export interface SpeedClassMetrics {
  avg_speed_kmh: number;
  max_speed_kmh: number;
  p85_speed_kmh: number;
  samples: number;
  compliance_rate?: number;
}

export interface PedestrianEpisodeMetrics {
  count: number;
  completed: number;
  avg_wait_seconds: number | null;
  median_wait_seconds: number | null;
  p85_wait_seconds: number | null;
  avg_crossing_seconds: number | null;
  median_crossing_seconds: number | null;
}

export interface YieldingMetrics {
  opportunities: number;
  yielded: number;
  did_not_yield: number;
  unresolved: number;
  yielding_rate: number | null;
}

export interface PostEncroachmentMetrics {
  events: number;
  min_pet_seconds: number | null;
  median_pet_seconds: number | null;
  critical_events: number;
  critical_threshold_seconds: number;
}

export interface CrossingSafetyMetrics {
  pedestrian_episodes: PedestrianEpisodeMetrics;
  yielding: YieldingMetrics;
  post_encroachment: PostEncroachmentMetrics;
}

export interface Metrics {
  total_crossings: number;
  counts_by_class: Record<string, number>;
  counts_by_line: Record<string, number>;
  counts_by_direction: Record<string, number>;
  flow_rate_per_minute: number;
  speed_limit_kmh: number | null;
  speed_metrics_by_class: Record<string, SpeedClassMetrics>;
  /** Attached by the analyzer only when a zebra layer is configured. */
  crossing_safety?: CrossingSafetyMetrics;
}

export interface ZebraZoneMetrics {
  events: number;
  zebra_yielding_risk: number;
  zebra_crossing_violation: number;
  unique_objects_in_zone: number;
  max_objects_in_zone: number;
  max_vehicles_in_zone: number;
  max_pedestrians_in_zone: number;
  vehicle_approach_trends: Record<string, number>;
}

export interface ZebraMetrics {
  events: number;
  zebra_yielding_risk: number;
  zebra_crossing_violation: number;
  rider_filtered_pedestrians_count: number;
  by_zone: Record<string, ZebraZoneMetrics>;
}

export interface ObjectSummary {
  object_id: number;
  class: string;
  frames_seen: number;
  max_speed_kmh: number | null;
  avg_speed_kmh: number | null;
}

export interface AnalysisSummary {
  mode: string;
  camera_id: string;
  video: VideoMeta;
  calibration: Calibration;
  counting_lines: unknown[];
  zebra_zones: unknown[];
  metrics: Metrics;
  zebra_metrics: ZebraMetrics;
  objects: ObjectSummary[];
  /** Local filesystem paths from the backend; the dashboard uses the envelope's artifact resolver instead. */
  outputs: Partial<Record<string, string>>;
}

// ---------------------------------------------------------------------------
// Typed CSV rows (columns match src/video_analysis/serializer.py exactly)
// ---------------------------------------------------------------------------

export interface CrossingRow {
  camera_id: string;
  line_id: string;
  line_label: string;
  object_id: string;
  class: string;
  direction: string;
  timestamp: string;
  frame_number: string;
  elapsed_seconds: string;
  source: string;
}

export interface TrackRow {
  frame_number: string;
  elapsed_seconds: string;
  camera_id: string;
  object_id: string;
  class: string;
  confidence: string;
  bbox: string;
  speed_kmh: string;
  is_rider: string;
  associated_vehicle_id: string;
  zebra_zone_id: string;
  inside_zebra: string;
  near_zebra: string;
  distance_to_zebra_m: string;
  inside_zebra_zone_ids: string;
  near_zebra_zone_ids: string;
}

export interface ZebraEventRow {
  event_type: string;
  camera_id: string;
  frame_number: string;
  elapsed_seconds: string;
  zone_id: string;
  vehicle_object_id: string;
  vehicle_class: string;
  vehicle_speed_kmh: string;
  vehicle_distance_to_zebra_m: string;
  pedestrian_object_id: string;
  pedestrian_speed_kmh: string;
  pedestrian_distance_to_zebra_m: string;
  vehicle_speed_trend: string;
  approach_start_speed_kmh: string;
  approach_end_speed_kmh: string;
  approach_delta_kmh: string;
  approach_samples: string;
  rider_filtered_pedestrians_count: string;
}

export interface ZebraOccupancyRow {
  frame_number: string;
  elapsed_seconds: string;
  zone_id: string;
  objects_in_zone: string;
  vehicles_in_zone: string;
  pedestrians_in_zone: string;
  bikes_in_zone: string;
  class_counts_json: string;
}

export interface PedestrianEpisodeRow {
  camera_id: string;
  zone_id: string;
  pedestrian_object_id: string;
  wait_start_seconds: string;
  crossing_start_seconds: string;
  crossing_end_seconds: string;
  wait_seconds: string;
  crossing_seconds: string;
  outcome: string;
}

export interface YieldingEventRow {
  camera_id: string;
  zone_id: string;
  vehicle_object_id: string;
  vehicle_class: string;
  opened_seconds: string;
  resolved_seconds: string;
  approach_speed_kmh: string;
  min_approach_speed_kmh: string;
  outcome: string;
  pedestrians_active: string;
}

export interface PetEventRow {
  camera_id: string;
  zone_id: string;
  first_object_id: string;
  first_class: string;
  second_object_id: string;
  second_class: string;
  first_exit_seconds: string;
  second_entry_seconds: string;
  pet_seconds: string;
  encroachment_order: string;
  second_speed_kmh: string;
  critical: string;
}

/** Maps a CSV artifact name to its row type. */
export interface CsvRowTypes {
  crossings_csv: CrossingRow;
  tracks_csv: TrackRow;
  zebra_events_csv: ZebraEventRow;
  zebra_occupancy_csv: ZebraOccupancyRow;
  pedestrian_episodes_csv: PedestrianEpisodeRow;
  yielding_events_csv: YieldingEventRow;
  pet_events_csv: PetEventRow;
}

export type CsvArtifactName = keyof CsvRowTypes;

// ---------------------------------------------------------------------------
// Dashboard job envelope (source-agnostic)
// ---------------------------------------------------------------------------

export type JobSource = "api" | "file";

export type JobStatus =
  | "draft"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "expired"
  | "deleted";

/**
 * The single shape every view consumes. `summary` is present once the job is
 * completed. `artifacts` resolves an artifact name to a URL that works for
 * this source (an API endpoint URL, or an object URL for an imported blob),
 * and `loadCsv` parses a CSV artifact into typed rows on demand.
 */
export interface DashboardJob {
  source: JobSource;
  jobId: string;
  label: string | null;
  cameraId: string | null;
  originalFilename: string | null;
  status: JobStatus;
  createdAt: string | null;
  completedAt: string | null;
  summary: AnalysisSummary | null;
  /** Artifact names available for this job (zebra artifacts only when present). */
  availableArtifacts: ArtifactName[];
  /** Resolve an artifact to a fetchable URL, or null if unavailable for this source. */
  artifactUrl(name: ArtifactName): string | null;
  /** Fetch + parse a CSV artifact into typed rows, or [] if unavailable. */
  loadCsv<N extends CsvArtifactName>(name: N): Promise<CsvRowTypes[N][]>;
}
