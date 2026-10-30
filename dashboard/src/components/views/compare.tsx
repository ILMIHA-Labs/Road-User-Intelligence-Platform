"use client";

import { useMemo, useState } from "react";
import { GroupedBar } from "@/components/charts-ext/grouped-bar";
import { cn } from "@/lib/utils";
import type { DashboardJob } from "@/data/types";

const JOB_COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];

type Direction = "up" | "down" | null;

interface MetricDef {
  key: string;
  label: string;
  unit?: string;
  digits?: number;
  /** Which way is "better", for delta coloring. */
  good: Direction;
  get: (job: DashboardJob) => number | null;
}

const METRICS: MetricDef[] = [
  { key: "crossings", label: "Total crossings", good: null, get: (j) => j.summary?.metrics.total_crossings ?? null },
  { key: "flow", label: "Flow rate", unit: "/min", digits: 1, good: null, get: (j) => j.summary?.metrics.flow_rate_per_minute ?? null },
  { key: "avgcar", label: "Avg car speed", unit: "km/h", digits: 1, good: "down", get: (j) => j.summary?.metrics.speed_metrics_by_class.car?.avg_speed_kmh ?? null },
  { key: "compliance", label: "Car compliance", unit: "%", good: "up", get: (j) => { const c = j.summary?.metrics.speed_metrics_by_class.car?.compliance_rate; return c == null ? null : c * 100; } },
  { key: "yield", label: "Yielding rate", unit: "%", good: "up", get: (j) => { const y = j.summary?.metrics.crossing_safety?.yielding.yielding_rate; return y == null ? null : y * 100; } },
  { key: "violations", label: "Crossing violations", good: "down", get: (j) => j.summary?.zebra_metrics.zebra_crossing_violation ?? null },
  { key: "pet", label: "Critical PET events", good: "down", get: (j) => j.summary?.metrics.crossing_safety?.post_encroachment.critical_events ?? null },
  { key: "wait", label: "Median ped wait", unit: "s", digits: 1, good: "down", get: (j) => j.summary?.metrics.crossing_safety?.pedestrian_episodes.median_wait_seconds ?? null },
];

function fmt(n: number | null, digits = 0): string {
  return n === null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function CompareView({ jobs }: { jobs: DashboardJob[] }) {
  const [selected, setSelected] = useState<string[]>(jobs.slice(0, 2).map((j) => j.jobId));

  const chosen = jobs.filter((j) => selected.includes(j.jobId));
  const color = (job: DashboardJob) => JOB_COLORS[jobs.indexOf(job) % JOB_COLORS.length];

  const classRows = useMemo(() => {
    const classes = new Set<string>();
    for (const j of chosen) for (const c of Object.keys(j.summary?.metrics.counts_by_class ?? {})) classes.add(c);
    return [...classes]
      .map((name) => {
        const row: Record<string, unknown> = { name };
        for (const j of chosen) row[j.jobId] = j.summary?.metrics.counts_by_class[name] ?? 0;
        return row;
      })
      .sort((a, b) => {
        const sum = (r: Record<string, unknown>) => chosen.reduce((t, j) => t + Number(r[j.jobId] ?? 0), 0);
        return sum(b) - sum(a);
      });
  }, [chosen]);

  if (jobs.length < 2) {
    return (
      <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
        Load at least two completed jobs to compare.
      </div>
    );
  }

  const baseline = chosen[0];
  const showDelta = chosen.length === 2;

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-medium">Jobs to compare</h2>
        <div className="flex flex-wrap gap-2">
          {jobs.map((j) => {
            const on = selected.includes(j.jobId);
            return (
              <button
                key={j.jobId}
                onClick={() =>
                  setSelected((prev) =>
                    prev.includes(j.jobId) ? prev.filter((id) => id !== j.jobId) : [...prev, j.jobId],
                  )
                }
                className={cn(
                  "flex items-center gap-2 rounded-full border px-3 py-1 text-xs transition-colors",
                  on ? "border-foreground" : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: on ? color(j) : "transparent", border: on ? undefined : "1px solid var(--border)" }} />
                {j.label ?? j.cameraId}
              </button>
            );
          })}
        </div>
      </section>

      {chosen.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
          Select at least one job.
        </div>
      ) : (
        <>
          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="mb-3 text-sm font-medium">Metrics</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Metric</th>
                    {chosen.map((j) => (
                      <th key={j.jobId} className="py-2 pr-4 text-right font-medium">
                        <span className="inline-flex items-center gap-1.5">
                          <span className="h-2 w-2 rounded-full" style={{ background: color(j) }} />
                          {j.label ?? j.cameraId}
                        </span>
                      </th>
                    ))}
                    {showDelta ? <th className="py-2 text-right font-medium">Δ</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map((m) => {
                    const base = m.get(baseline);
                    return (
                      <tr key={m.key} className="border-b border-border/60 last:border-0">
                        <td className="py-2 pr-4">{m.label}</td>
                        {chosen.map((j) => (
                          <td key={j.jobId} className="py-2 pr-4 text-right tabular-nums">
                            {fmt(m.get(j), m.digits)}
                            {m.unit ? <span className="text-muted-foreground"> {m.unit}</span> : null}
                          </td>
                        ))}
                        {showDelta ? <DeltaCell base={base} other={m.get(chosen[1])} digits={m.digits} good={m.good} /> : null}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="mb-3 text-sm font-medium">Crossings by class</h2>
            <GroupedBar
              data={classRows}
              series={chosen.map((j) => ({ key: j.jobId, label: j.label ?? j.cameraId ?? j.jobId, fill: color(j) }))}
            />
          </section>
        </>
      )}
    </div>
  );
}

function DeltaCell({ base, other, digits = 0, good }: { base: number | null; other: number | null; digits?: number; good: Direction }) {
  if (base === null || other === null) return <td className="py-2 text-right text-muted-foreground">—</td>;
  const diff = other - base;
  const sign = diff > 0 ? "+" : "";
  let tone = "text-muted-foreground";
  if (good && diff !== 0) {
    const improved = good === "up" ? diff > 0 : diff < 0;
    tone = improved ? "text-emerald-600 dark:text-emerald-400" : "text-destructive";
  }
  return (
    <td className={cn("py-2 text-right tabular-nums", tone)}>
      {sign}
      {diff.toLocaleString(undefined, { maximumFractionDigits: digits })}
    </td>
  );
}
