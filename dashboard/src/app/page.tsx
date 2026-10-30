"use client";

import { AppShell } from "@/components/app-shell";
import { SAMPLE_JOBS } from "@/data/sample";

export default function Home() {
  return <AppShell jobs={SAMPLE_JOBS} />;
}
