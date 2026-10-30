"use client";

import { useState } from "react";
import { ChatPanel } from "@/components/assistant/chat-panel";
import { OverviewView } from "@/components/views/overview";
import { ZebraSafetyView } from "@/components/views/zebra-safety";
import { cn } from "@/lib/utils";
import type { DashboardJob } from "@/data/types";

const VIEWS = [
  { id: "overview", label: "Overview", ready: true },
  { id: "zebra", label: "Zebra safety", ready: true },
  { id: "speed", label: "Speed", ready: false },
  { id: "objects", label: "Objects", ready: false },
  { id: "video", label: "Annotated video", ready: false },
  { id: "compare", label: "Compare", ready: false },
] as const;

type ViewId = (typeof VIEWS)[number]["id"];

export function AppShell({ job }: { job: DashboardJob }) {
  const [active, setActive] = useState<ViewId>("overview");
  const [chatOpen, setChatOpen] = useState(false);
  const s = job.summary;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6">
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight">
            {job.label ?? job.cameraId ?? "Analysis"}
          </h1>
          <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
            {job.source === "api" ? "live API" : "imported file"}
          </span>
          <button
            onClick={() => setChatOpen((v) => !v)}
            aria-pressed={chatOpen}
            className={cn(
              "ml-auto rounded-md border px-3 py-1.5 text-sm transition-colors",
              chatOpen
                ? "border-foreground bg-foreground text-background"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            Assistant
          </button>
        </div>
        {s ? (
          <p className="mt-1 text-sm text-muted-foreground">
            {job.cameraId} · {(s.video.duration_seconds / 60).toFixed(1)} min ·{" "}
            {s.video.width}×{s.video.height} · calibration: {s.calibration.source}
          </p>
        ) : null}
      </header>

      <nav className="mb-6 flex flex-wrap gap-1 border-b border-border">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            onClick={() => setActive(v.id)}
            className={cn(
              "relative px-3 py-2 text-sm transition-colors",
              active === v.id
                ? "font-medium text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {v.label}
            {!v.ready ? (
              <span className="ml-1 text-[10px] uppercase text-muted-foreground/60">soon</span>
            ) : null}
            {active === v.id ? (
              <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-foreground" />
            ) : null}
          </button>
        ))}
      </nav>

      <div className={cn(chatOpen && "lg:grid lg:grid-cols-[1fr_380px] lg:gap-6")}>
        <main>
          {active === "overview" ? <OverviewView job={job} /> : null}
          {active === "zebra" ? <ZebraSafetyView job={job} /> : null}
          {active !== "overview" && active !== "zebra" ? <Planned /> : null}
        </main>
        {chatOpen ? (
          <aside className="mt-6 lg:mt-0">
            <div className="lg:sticky lg:top-6 h-[32rem] lg:h-[calc(100vh-7rem)]">
              <ChatPanel job={job} />
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}

function Planned() {
  return (
    <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
      Planned view — part of the view catalogue (ticket #18). The Overview and
      Zebra safety views are prototyped; the rest follow once this layout is
      approved.
    </div>
  );
}
