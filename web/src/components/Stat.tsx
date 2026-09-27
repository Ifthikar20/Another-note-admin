/**
 * Stat tiles: a label, a value, a line of context. Values use proportional figures (they
 * stand alone); a budget shows as a meter whose colour carries its state, with the state
 * also written out.
 */
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";

export function StatGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4", className)}>{children}</div>;
}

export function StatTile({
  label,
  value,
  sub,
  to,
  children,
  className,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  to?: string;
  children?: ReactNode;
  className?: string;
}) {
  const body = (
    <>
      <p className="text-[12px] font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight">{value}</p>
      {sub ? <div className="mt-0.5 text-[12px] text-muted-foreground">{sub}</div> : null}
      {children}
    </>
  );
  const classes = cn("block rounded-lg border bg-card px-4 py-3", to && "transition-colors hover:bg-muted/50", className);
  return to ? (
    <Link to={to} className={classes}>
      {body}
    </Link>
  ) : (
    <div className={classes}>{body}</div>
  );
}

/** Spend against a budget: accent under 80%, warning to 100%, critical past it. */
export function BudgetMeter({ spent, budget }: { spent: number | null; budget: number | null }) {
  if (spent === null || !budget) {
    return <p className="mt-2 text-[12px] text-muted-foreground">{budget ? "Prices not set yet" : "No monthly budget set"}</p>;
  }
  const ratio = spent / budget;
  const state = ratio >= 1 ? "Over budget" : ratio >= 0.8 ? "Near budget" : "Within budget";
  const color = ratio >= 1 ? "var(--viz-critical)" : ratio >= 0.8 ? "hsl(var(--warning))" : "var(--viz-accent)";
  return (
    <div className="mt-2">
      <div
        className="h-1.5 w-full overflow-hidden rounded-full"
        style={{ background: `color-mix(in srgb, ${color} 18%, transparent)` }}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={budget}
        aria-valuenow={spent}
        aria-label="Spend against the monthly budget"
      >
        <div className="h-full rounded-full" style={{ width: `${Math.min(100, ratio * 100)}%`, background: color }} />
      </div>
      <p className="mt-1 text-[12px] text-muted-foreground">
        {state}: {Math.round(ratio * 100)}% of ${budget.toLocaleString("en-US")}
      </p>
    </div>
  );
}
