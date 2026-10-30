"use client";

import { Bar } from "@/components/charts/bar";
import { BarChart } from "@/components/charts/bar-chart";
import { BarXAxis } from "@/components/charts/bar-x-axis";
import { Grid } from "@/components/charts/grid";
import { ChartTooltip } from "@/components/charts/tooltip";

export interface CountsDatum {
  name: string;
  value: number;
}

export interface CountsBarProps {
  data: CountsDatum[];
  fill?: string;
  unit?: string;
  aspectRatio?: string;
}

/** A simple categorical bar chart (counts by class / zone) built on Bklit. */
export function CountsBar({
  data,
  fill = "var(--chart-1)",
  unit = "",
  aspectRatio = "5 / 2",
}: CountsBarProps) {
  return (
    <BarChart
      data={data as unknown as Record<string, unknown>[]}
      xDataKey="name"
      aspectRatio={aspectRatio}
      barGap={0.35}
    >
      <Grid horizontal />
      <Bar dataKey="value" fill={fill} lineCap={6} />
      <BarXAxis showAllLabels />
      <ChartTooltip
        rows={(point) => [
          {
            color: fill,
            label: String(point.name ?? ""),
            value: `${Number(point.value ?? 0).toLocaleString()}${unit}`,
          },
        ]}
      />
    </BarChart>
  );
}
