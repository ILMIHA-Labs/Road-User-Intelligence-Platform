"use client";

import { AppShell } from "@/components/app-shell";
import { SAMPLE_JOB } from "@/data/sample";

export default function Home() {
  return <AppShell job={SAMPLE_JOB} />;
}
