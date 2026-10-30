import { cn } from "@/lib/utils";

export interface StatTileProps {
  label: string;
  value: string | number;
  unit?: string;
  hint?: string;
  accent?: string;
  className?: string;
}

export function StatTile({ label, value, unit, hint, accent, className }: StatTileProps) {
  return (
    <div className={cn("rounded-lg border border-border bg-card p-4", className)}>
      <div className="flex items-center gap-2">
        {accent ? (
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: accent }} />
        ) : null}
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight">
        {value}
        {unit ? <span className="ml-1 text-base font-normal text-muted-foreground">{unit}</span> : null}
      </p>
      {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
