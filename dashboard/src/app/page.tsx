export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-6 px-4 py-16">
      <div className="space-y-3">
        <span className="inline-block rounded-full border border-border px-3 py-1 text-xs text-muted-foreground">
          RUIP · Offline analytics
        </span>
        <h1 className="text-3xl font-semibold tracking-tight">
          Analytics Dashboard
        </h1>
        <p className="text-muted-foreground">
          Visualizes offline video-analysis job outputs — object counts, zebra
          crossing safety, speed, and tracks — with a Claude-grounded chat and
          voice Q&amp;A. Scaffold ready; chart components install from the
          Kokonut and Bklit registries once network access is granted.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[1, 2, 3, 4, 5].map((n) => (
          <div
            key={n}
            className="h-16 rounded-lg border border-border"
            style={{ background: `var(--chart-${n})` }}
            title={`--chart-${n}`}
          />
        ))}
      </div>
    </main>
  );
}
