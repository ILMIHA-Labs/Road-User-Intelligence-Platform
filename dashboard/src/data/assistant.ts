/**
 * Chat assistant contract + helpers, shared by the client and the proxy route
 * (wayfinder #15). The proxy is a Next route handler so the Anthropic key stays
 * server-side. Grounding is DPG-safe: only aggregate metrics are ever sent —
 * never frames, footage, or per-individual rows.
 */
import type { DashboardJob, Metrics, ZebraMetrics } from "./types";

export type ChatRole = "user" | "assistant";
export interface ChatMessage {
  role: ChatRole;
  content: string;
}

/** Model tiers the UI may request; the server maps these to concrete IDs. */
export type AssistantModelTier = "opus" | "sonnet" | "haiku";

export const MODEL_IDS: Record<AssistantModelTier, string> = {
  opus: "claude-opus-5-5",
  sonnet: "claude-sonnet-5-5",
  haiku: "claude-haiku-5-5",
};

export const DEFAULT_MODEL_TIER: AssistantModelTier = "opus";

/** Aggregate-only snapshot of a job used to ground answers. No PII, no frames. */
export interface GroundingJob {
  label: string | null;
  cameraId: string | null;
  source: string;
  video: { duration_seconds: number; fps: number; width: number; height: number };
  calibration: { source: string; pixels_per_meter?: number | null };
  metrics: Metrics;
  zebra_metrics: ZebraMetrics;
  objectCount: number;
}

export interface AssistantContext {
  /** One job, or several when comparing. */
  jobs: GroundingJob[];
}

export interface ChatRequest {
  messages: ChatMessage[];
  context: AssistantContext;
  model?: AssistantModelTier;
}

/** Build a DPG-safe grounding snapshot from a job — aggregates only. */
export function buildGroundingJob(job: DashboardJob): GroundingJob | null {
  const s = job.summary;
  if (!s) return null;
  return {
    label: job.label,
    cameraId: job.cameraId,
    source: job.source,
    video: {
      duration_seconds: s.video.duration_seconds,
      fps: s.video.fps,
      width: s.video.width,
      height: s.video.height,
    },
    calibration: { source: s.calibration.source, pixels_per_meter: s.calibration.pixels_per_meter ?? null },
    metrics: s.metrics,
    zebra_metrics: s.zebra_metrics,
    objectCount: s.objects.length,
  };
}

export function buildContext(jobs: DashboardJob[]): AssistantContext {
  return { jobs: jobs.map(buildGroundingJob).filter((j): j is GroundingJob => j !== null) };
}

/** System prompt: grounds the model in the aggregates and forbids guessing. */
export function buildSystemPrompt(context: AssistantContext): string {
  return [
    "You are the analytics assistant for the Road User Intelligence Platform,",
    "a traffic and zebra-crossing video-analysis tool.",
    "Answer ONLY from the JSON metrics below. They are aggregate measurements;",
    "you have no access to video frames, images, or per-individual data.",
    "If a question cannot be answered from these metrics, say so plainly.",
    "Be concise and cite the specific numbers you used. Speeds are km/h,",
    "times are seconds. When several jobs are present, compare them explicitly.",
    "",
    "METRICS:",
    JSON.stringify(context.jobs, null, 2),
  ].join("\n");
}

/**
 * Client helper: POST to the proxy and stream the plain-text answer.
 * Calls `onToken` for each chunk; resolves with the full text.
 */
export async function streamAssistant(
  req: ChatRequest,
  onToken: (chunk: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  const res = await fetch("/api/assistant/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(detail.error ?? `Assistant error (${res.status})`);
  }
  if (!res.body) return "";
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let full = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    full += chunk;
    onToken(chunk);
  }
  return full;
}
