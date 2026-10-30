import { CountsBar } from "@/components/charts-ext/counts-bar";
import { StatTile } from "@/components/ui/stat-tile";
import type { DashboardJob } from "@/data/types";

const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

function fmt(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function OverviewView({ job }: { job: DashboardJob }) {
  const s = job.summary;
  if (!s) return <Empty />;
  const m = s.metrics;

  const classCounts = Object.entries(m.counts_by_class)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  const car = m.speed_metrics_by_class.car;

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Total crossings" value={fmt(m.total_crossings)} accent={CHART_COLORS[0]} />
        <StatTile label="Flow rate" value={fmt(m.flow_rate_per_minute, 1)} unit="/min" accent={CHART_COLORS[1]} />
        <StatTile label="Objects tracked" value={fmt(s.objects.length)} accent={CHART_COLORS[2]} />
        <StatTile
          label="Avg car speed"
          value={fmt(car?.avg_speed_kmh, 1)}
          unit="km/h"
          hint={m.speed_limit_kmh ? `limit ${m.speed_limit_kmh} km/h` : undefined}
          accent={CHART_COLORS[3]}
        />
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-1 text-sm font-medium">Crossings by class</h2>
        <p className="mb-3 text-xs text-muted-foreground">
          {fmt(m.total_crossings)} crossings over {fmt(s.video.duration_seconds / 60, 1)} min
        </p>
        <CountsBar data={classCounts} unit=" crossings" />
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-medium">Speed by class</h2>
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
              {Object.entries(m.speed_metrics_by_class).map(([cls, sp]) => (
                <tr key={cls} className="border-b border-border/60 last:border-0">
                  <td className="py-2 pr-4 capitalize">{cls}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmt(sp.avg_speed_kmh, 1)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmt(sp.p85_speed_kmh, 1)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmt(sp.max_speed_kmh, 1)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {sp.compliance_rate != null ? `${fmt(sp.compliance_rate * 100)}%` : "—"}
                  </td>
                  <td className="py-2 text-right tabular-nums text-muted-foreground">{fmt(sp.samples)}</td>
                </tr>
              ))}
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
