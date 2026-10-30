"use client";

import { Bar } from "@/components/charts/bar";
import { BarChart } from "@/components/charts/bar-chart";
import { BarXAxis } from "@/components/charts/bar-x-axis";
import { Grid } from "@/components/charts/grid";
import { ChartTooltip } from "@/components/charts/tooltip";

export interface GroupedSeries {
  key: string;
  label: string;
  fill: string;
}

export interface GroupedBarProps {
  /** Each row has an x-axis `name` plus one numeric value per series key. */
  data: Record<string, unknown>[];
  series: GroupedSeries[];
  aspectRatio?: string;
}

/** Grouped categorical bars (one series per job) built on Bklit. */
export function GroupedBar({ data, series, aspectRatio = "5 / 2" }: GroupedBarProps) {
  return (
    <BarChart data={data} xDataKey="name" aspectRatio={aspectRatio} barGap={0.4}>
      <Grid horizontal />
      {series.map((s) => (
        <Bar key={s.key} dataKey={s.key} fill={s.fill} lineCap={4} />
      ))}
      <BarXAxis showAllLabels />
      <ChartTooltip
        rows={(point) =>
          series.map((s) => ({
            color: s.fill,
            label: s.label,
            value: Number(point[s.key] ?? 0).toLocaleString(),
          }))
        }
      />
    </BarChart>
  );
}
