import { CountsBar } from "@/components/charts-ext/counts-bar";
import { StatTile } from "@/components/ui/stat-tile";
import { cn } from "@/lib/utils";
import type { DashboardJob } from "@/data/types";

function fmt(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function SpeedView({ job }: { job: DashboardJob }) {
  const s = job.summary;
  if (!s) return <Empty />;
  const m = s.metrics;
  const limit = m.speed_limit_kmh;
  const entries = Object.entries(m.speed_metrics_by_class);

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
        No speed samples in this analysis.
      </div>
    );
  }

  const fastest = entries.reduce((a, b) => (b[1].max_speed_kmh > a[1].max_speed_kmh ? b : a));
  const withCompliance = entries.filter(([, v]) => v.compliance_rate != null);
  const lowestCompliance =
    withCompliance.length > 0
      ? withCompliance.reduce((a, b) => (b[1].compliance_rate! < a[1].compliance_rate! ? b : a))
      : null;

  const avgByClass = entries
    .map(([name, v]) => ({ name, value: Math.round(v.avg_speed_kmh * 10) / 10 }))
    .sort((a, b) => b.value - a.value);

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Speed limit" value={limit != null ? fmt(limit) : "—"} unit="km/h" accent="var(--chart-4)" />
        <StatTile label="Classes measured" value={fmt(entries.length)} accent="var(--chart-2)" />
        <StatTile label="Fastest (max)" value={fmt(fastest[1].max_speed_kmh, 1)} unit="km/h" hint={fastest[0]} accent="var(--chart-5)" />
        <StatTile
          label="Lowest compliance"
          value={lowestCompliance ? `${fmt(lowestCompliance[1].compliance_rate! * 100)}%` : "—"}
          hint={lowestCompliance?.[0]}
          accent="var(--chart-3)"
        />
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-1 text-sm font-medium">Average speed by class</h2>
        <p className="mb-3 text-xs text-muted-foreground">
          {limit != null ? `Speed limit ${limit} km/h` : "No speed limit configured"}
        </p>
        <CountsBar data={avgByClass} unit=" km/h" fill="var(--chart-4)" />
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-medium">Speed detail</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2 pr-4 font-medium">Class</th>
                <th className="py-2 pr-4 text-right font-medium">Avg</th>
                <th className="py-2 pr-4 text-right font-medium">P85</th>
                <th className="py-2 pr-4 text-right font-medium">Max</th>
                <th className="py-2 pr-4 text-right font-medium">Compliance</th>
                <th className="py-2 text-right font-medium">Samples</th>
              </tr>
            </thead>
            <tbody>
              {entries
                .sort((a, b) => b[1].p85_speed_kmh - a[1].p85_speed_kmh)
                .map(([cls, sp]) => {
                  const overLimit = limit != null && sp.p85_speed_kmh > limit;
                  return (
                    <tr key={cls} className="border-b border-border/60 last:border-0">
                      <td className="py-2 pr-4 capitalize">
                        {cls}
                        {overLimit ? (
                          <span className="ml-2 rounded-full bg-destructive/10 px-1.5 py-0.5 text-[10px] font-medium text-destructive">
                            P85 over limit
                          </span>
                        ) : null}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums">{fmt(sp.avg_speed_kmh, 1)}</td>
                      <td className={cn("py-2 pr-4 text-right tabular-nums", overLimit && "text-destructive")}>
                        {fmt(sp.p85_speed_kmh, 1)}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums">{fmt(sp.max_speed_kmh, 1)}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">
                        {sp.compliance_rate != null ? `${fmt(sp.compliance_rate * 100)}%` : "—"}
                      </td>
                      <td className="py-2 text-right tabular-nums text-muted-foreground">{fmt(sp.samples)}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Empty() {
  return (
    <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
      No completed analysis loaded.
    </div>
  );
}
