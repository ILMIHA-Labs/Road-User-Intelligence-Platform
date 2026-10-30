/**
 * Live-API client. Calls the backend same-origin at `/api/v1` by default, which
 * the Next dev rewrite (and, in prod, the reverse proxy) forwards to the Python
 * FastAPI backend — so there is no CORS to configure (#17). Point
 * NEXT_PUBLIC_API_BASE_URL at a full origin to call a remote API directly
 * (that path does need CORS on the backend).
 */
import { type ApiJob, fromApiJob } from "./adapters";
import type { DashboardJob } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal });
  if (!res.ok) {
    throw new Error(`API request failed (${res.status}) for ${path}`);
  }
  return (await res.json()) as T;
}

/** List recent analysis jobs as source-agnostic DashboardJobs. */
export async function listApiJobs(signal?: AbortSignal): Promise<DashboardJob[]> {
  const data = await getJson<{ jobs: ApiJob[] }>("/video-analysis/jobs", signal);
  return (data.jobs ?? []).map((job) => fromApiJob(job, API_BASE));
}

/** Fetch a single analysis job (with its result summary when completed). */
export async function getApiJob(jobId: string, signal?: AbortSignal): Promise<DashboardJob> {
  const job = await getJson<ApiJob>(`/video-analysis/jobs/${encodeURIComponent(jobId)}`, signal);
  return fromApiJob(job, API_BASE);
}
