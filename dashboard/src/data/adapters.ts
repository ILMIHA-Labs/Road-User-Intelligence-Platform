/**
 * Adapters that build a source-agnostic `DashboardJob` from each source:
 * the live API (`fromApiJob`) and imported export files (`fromSummaryFile`).
 * Both produce the same envelope so every view is source-agnostic (#14).
 */
import { parseCsv } from "./csv";
import {
  ARTIFACT_NAMES,
  ZEBRA_ARTIFACT_NAMES,
  type AnalysisSummary,
  type ArtifactName,
  type CsvArtifactName,
  type CsvRowTypes,
  type DashboardJob,
  type JobStatus,
} from "./types";

/** The raw job object as serialized by the backend `_serialize_video_analysis_job`. */
export interface ApiJob {
  job_id: string;
  label: string | null;
  camera_id: string | null;
  original_filename: string | null;
  status: string;
  created_at: string | null;
  completed_at: string | null;
  result_summary: AnalysisSummary | null;
  artifacts: Partial<Record<ArtifactName, string>>;
  [key: string]: unknown;
}

function isArtifactName(name: string): name is ArtifactName {
  return (ARTIFACT_NAMES as readonly string[]).includes(name);
}

/**
 * Build a DashboardJob from an API job.
 * @param apiBase base URL the artifact endpoints are served from (e.g. "/api/v1").
 */
export function fromApiJob(apiJob: ApiJob, apiBase = ""): DashboardJob {
  const base = apiBase.replace(/\/$/, "");
  const urls = apiJob.artifacts ?? {};
  const available = (Object.keys(urls) as string[]).filter(isArtifactName);

  const artifactUrl = (name: ArtifactName): string | null => {
    const path = urls[name];
    return path ? `${base}${path}` : null;
  };

  return {
    source: "api",
    jobId: apiJob.job_id,
    label: apiJob.label ?? null,
    cameraId: apiJob.camera_id ?? null,
    originalFilename: apiJob.original_filename ?? null,
    status: (apiJob.status as JobStatus) ?? "draft",
    createdAt: apiJob.created_at ?? null,
    completedAt: apiJob.completed_at ?? null,
    summary: apiJob.result_summary ?? null,
    availableArtifacts: available,
    artifactUrl,
    async loadCsv<N extends CsvArtifactName>(name: N): Promise<CsvRowTypes[N][]> {
      const url = artifactUrl(name);
      if (!url) return [];
      const res = await fetch(url);
      if (!res.ok) return [];
      return parseCsv<CsvRowTypes[N]>(await res.text());
    },
  };
}

/**
 * Build a DashboardJob from imported files. The summary is required; artifact
 * blobs (annotated video, CSVs) are optional — pass whatever the user supplied
 * (e.g. the contents of an exported folder or an unzipped research bundle).
 */
export function fromSummaryFile(
  summary: AnalysisSummary,
  options: {
    files?: Partial<Record<ArtifactName, Blob>>;
    jobId?: string;
    label?: string | null;
    originalFilename?: string | null;
  } = {},
): DashboardJob {
  const files = options.files ?? {};
  const objectUrls = new Map<ArtifactName, string>();

  const hasZebra =
    summary.zebra_metrics && summary.zebra_metrics.events > 0;
  const available = ARTIFACT_NAMES.filter((name) => {
    if (name === "summary_json") return true;
    if (files[name]) return true;
    // If no blobs were provided, advertise the non-zebra artifacts the
    // summary implies so views can still reason about what exists.
    if (Object.keys(files).length === 0) {
      return !ZEBRA_ARTIFACT_NAMES.has(name) || hasZebra;
    }
    return false;
  });

  const artifactUrl = (name: ArtifactName): string | null => {
    const blob = files[name];
    if (!blob) return null;
    let url = objectUrls.get(name);
    if (!url) {
      url = URL.createObjectURL(blob);
      objectUrls.set(name, url);
    }
    return url;
  };

  return {
    source: "file",
    jobId: options.jobId ?? `file:${summary.camera_id}:${summary.video?.path ?? "import"}`,
    label: options.label ?? summary.camera_id ?? null,
    cameraId: summary.camera_id ?? null,
    originalFilename: options.originalFilename ?? null,
    status: "completed",
    createdAt: null,
    completedAt: null,
    summary,
    availableArtifacts: available,
    artifactUrl,
    async loadCsv<N extends CsvArtifactName>(name: N): Promise<CsvRowTypes[N][]> {
      const blob = files[name];
      if (!blob) return [];
      return parseCsv<CsvRowTypes[N]>(await blob.text());
    },
  };
}
