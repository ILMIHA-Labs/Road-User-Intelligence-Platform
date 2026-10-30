import type { DashboardJob } from "@/data/types";

export function AnnotatedVideoView({ job }: { job: DashboardJob }) {
  const url = job.artifactUrl("annotated_video");

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-medium">Annotated video</h2>
        {url ? (
          <video
            controls
            src={url}
            className="aspect-video w-full rounded-md border border-border bg-black"
          />
        ) : (
          <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border text-center">
            <p className="text-sm text-muted-foreground">
              The annotated video isn&apos;t attached to this job.
            </p>
            <p className="max-w-md text-xs text-muted-foreground">
              It plays here when a completed job exposes the{" "}
              <code className="rounded bg-muted px-1">annotated_video</code> artifact —
              from the live API, or an imported export that includes{" "}
              <code className="rounded bg-muted px-1">annotated.mp4</code>.
            </p>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-2 text-sm font-medium">Artifacts for this job</h2>
        <div className="flex flex-wrap gap-2">
          {job.availableArtifacts.map((name) => {
            const has = job.artifactUrl(name) !== null;
            return (
              <span
                key={name}
                className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground"
                title={has ? "available" : "declared by the job, not fetchable in this source"}
              >
                {name}
                {has ? <span className="ml-1 text-emerald-600 dark:text-emerald-400">●</span> : null}
              </span>
            );
          })}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          A future enhancement overlays event markers (violations, crossings, PET)
          on the timeline using the event CSVs&apos; <code className="rounded bg-muted px-1">elapsed_seconds</code>.
        </p>
      </section>
    </div>
  );
}
