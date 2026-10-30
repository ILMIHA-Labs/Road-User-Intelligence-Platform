import { CountsBar } from "@/components/charts-ext/counts-bar";
import { StatTile } from "@/components/ui/stat-tile";
import type { DashboardJob } from "@/data/types";

function fmt(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

const MAX_ROWS = 50;

export function ObjectsView({ job }: { job: DashboardJob }) {
  const s = job.summary;
  if (!s) return <Empty />;
  const objects = s.objects;

  if (objects.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
        No tracked objects in this analysis.
      </div>
    );
  }

  const byClass = new Map<string, number>();
  for (const o of objects) byClass.set(o.class, (byClass.get(o.class) ?? 0) + 1);
  const classData = [...byClass.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  const rows = [...objects].sort((a, b) => b.frames_seen - a.frames_seen).slice(0, MAX_ROWS);

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Objects tracked" value={fmt(objects.length)} accent="var(--chart-1)" />
        <StatTile label="Classes present" value={fmt(byClass.size)} accent="var(--chart-2)" />
        <StatTile label="Total crossings" value={fmt(s.metrics.total_crossings)} accent="var(--chart-3)" />
        <StatTile
          label="Rider-filtered peds"
          value={fmt(s.zebra_metrics.rider_filtered_pedestrians_count)}
          hint="reclassified as riders"
          accent="var(--chart-4)"
        />
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-medium">Tracked objects by class</h2>
        <CountsBar data={classData} unit=" objects" fill="var(--chart-1)" />
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-sm font-medium">Tracks</h2>
          {objects.length > MAX_ROWS ? (
            <span className="text-xs text-muted-foreground">showing top {MAX_ROWS} of {objects.length}</span>
          ) : null}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2 pr-4 font-medium">ID</th>
                <th className="py-2 pr-4 font-medium">Class</th>
                <th className="py-2 pr-4 text-right font-medium">Frames seen</th>
                <th className="py-2 pr-4 text-right font-medium">Avg speed</th>
                <th className="py-2 text-right font-medium">Max speed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.object_id} className="border-b border-border/60 last:border-0">
                  <td className="py-2 pr-4 tabular-nums text-muted-foreground">#{o.object_id}</td>
                  <td className="py-2 pr-4 capitalize">{o.class}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmt(o.frames_seen)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmt(o.avg_speed_kmh, 1)}{o.avg_speed_kmh != null ? " km/h" : ""}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(o.max_speed_kmh, 1)}{o.max_speed_kmh != null ? " km/h" : ""}</td>
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
