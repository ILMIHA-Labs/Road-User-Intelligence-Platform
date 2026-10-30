import { CountsBar } from "@/components/charts-ext/counts-bar";
import { StatTile } from "@/components/ui/stat-tile";
import type { DashboardJob } from "@/data/types";

function fmt(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function ZebraSafetyView({ job }: { job: DashboardJob }) {
  const s = job.summary;
  if (!s) return <Empty />;
  const z = s.zebra_metrics;
  const safety = s.metrics.crossing_safety;

  if (!safety || z.events === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
        No zebra-crossing layer was configured for this job.
      </div>
    );
  }

  const yld = safety.yielding;
  const ep = safety.pedestrian_episodes;
  const pet = safety.post_encroachment;

  const trends = Object.entries(z.by_zone)[0]?.[1]?.vehicle_approach_trends ?? {};
  const trendData = Object.entries(trends).map(([name, value]) => ({ name, value }));

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile
          label="Yielding rate"
          value={yld.yielding_rate != null ? fmt(yld.yielding_rate * 100) : "—"}
          unit="%"
          hint={`${fmt(yld.yielded)} of ${fmt(yld.yielded + yld.did_not_yield)} decided`}
          accent="var(--chart-2)"
        />
        <StatTile
          label="Crossing violations"
          value={fmt(z.zebra_crossing_violation)}
          hint="vehicle entered occupied zebra"
          accent="var(--chart-5)"
        />
        <StatTile
          label="Yielding risks"
          value={fmt(z.zebra_yielding_risk)}
          hint="near-miss approaches"
          accent="var(--chart-4)"
        />
        <StatTile
          label="Critical PET events"
          value={fmt(pet.critical_events)}
          unit={`/ ${fmt(pet.events)}`}
          hint={`< ${pet.critical_threshold_seconds}s post-encroachment`}
          accent="var(--chart-3)"
        />
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="mb-3 text-sm font-medium">Pedestrian episodes</h2>
          <dl className="space-y-2 text-sm">
            <Row label="Episodes" value={`${fmt(ep.completed)} completed / ${fmt(ep.count)}`} />
            <Row label="Median wait" value={`${fmt(ep.median_wait_seconds, 1)} s`} />
            <Row label="P85 wait" value={`${fmt(ep.p85_wait_seconds, 1)} s`} />
            <Row label="Median crossing" value={`${fmt(ep.median_crossing_seconds, 1)} s`} />
          </dl>
        </section>

        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="mb-3 text-sm font-medium">Post-encroachment time</h2>
          <dl className="space-y-2 text-sm">
            <Row label="Events" value={fmt(pet.events)} />
            <Row label="Min PET" value={`${fmt(pet.min_pet_seconds, 1)} s`} />
            <Row label="Median PET" value={`${fmt(pet.median_pet_seconds, 1)} s`} />
            <Row label="Critical" value={`${fmt(pet.critical_events)} (< ${pet.critical_threshold_seconds}s)`} />
          </dl>
        </section>
      </div>

      {trendData.length > 0 ? (
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="mb-1 text-sm font-medium">Vehicle approach behaviour</h2>
          <p className="mb-3 text-xs text-muted-foreground">
            How vehicles changed speed on approach to the zebra
          </p>
          <CountsBar data={trendData} unit=" vehicles" fill="var(--chart-2)" aspectRatio="4 / 1" />
        </section>
      ) : null}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/60 pb-2 last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="tabular-nums font-medium">{value}</dd>
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
