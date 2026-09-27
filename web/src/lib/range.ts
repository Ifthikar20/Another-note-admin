/**
 * The date range a page shows, as whole UTC days, kept in the URL (?range=7d, or
 * ?from=2026-10-01&to=2026-10-31) so a link shows the same slice to a colleague.
 */
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export type Preset = "today" | "7d" | "30d" | "90d" | "mtd" | "custom";

export const PRESETS: { value: Exclude<Preset, "custom">; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "mtd", label: "Month to date" },
];

export interface DayRange {
  from: string;
  to: string;
  preset: Preset;
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export function utcDay(date: Date = new Date()): string {
  return date.toISOString().slice(0, 10);
}

export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return utcDay(d);
}

export function presetRange(preset: Exclude<Preset, "custom">, now: Date = new Date()): { from: string; to: string } {
  const today = utcDay(now);
  switch (preset) {
    case "today":
      return { from: today, to: today };
    case "7d":
      return { from: addDays(today, -6), to: today };
    case "90d":
      return { from: addDays(today, -89), to: today };
    case "mtd":
      return { from: `${today.slice(0, 8)}01`, to: today };
    case "30d":
    default:
      return { from: addDays(today, -29), to: today };
  }
}

/** Every UTC day from `from` to `to`, both included. */
export function daysBetween(from: string, to: string): string[] {
  const out: string[] = [];
  for (let d = from; d <= to && out.length < 400; d = addDays(d, 1)) out.push(d);
  return out;
}

export function rangeLabel(range: { from: string; to: string }): string {
  const fmt = (day: string, year: boolean) =>
    new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: year ? "numeric" : undefined, timeZone: "UTC" }).format(
      new Date(`${day}T00:00:00Z`),
    );
  if (range.from === range.to) return fmt(range.to, true);
  const sameYear = range.from.slice(0, 4) === range.to.slice(0, 4);
  return `${fmt(range.from, !sameYear)} – ${fmt(range.to, true)}`;
}

export function parseRange(params: URLSearchParams, fallback: Exclude<Preset, "custom">, now: Date = new Date()): DayRange {
  const from = params.get("from");
  const to = params.get("to");
  if (from && to && DAY.test(from) && DAY.test(to) && from <= to) return { from, to, preset: "custom" };
  const preset = params.get("range") as Preset | null;
  const known = PRESETS.find((p) => p.value === preset);
  const chosen = known ? known.value : fallback;
  return { ...presetRange(chosen, now), preset: chosen };
}

export function useRange(fallback: Exclude<Preset, "custom"> = "30d") {
  const [params, setParams] = useSearchParams();
  const range = useMemo(() => parseRange(params, fallback), [params, fallback]);
  const setRange = useCallback(
    (next: { preset: Exclude<Preset, "custom"> } | { from: string; to: string }) => {
      setParams(
        (current) => {
          const p = new URLSearchParams(current);
          p.delete("range");
          p.delete("from");
          p.delete("to");
          if ("preset" in next) {
            if (next.preset !== fallback) p.set("range", next.preset);
          } else {
            p.set("from", next.from);
            p.set("to", next.to);
          }
          return p;
        },
        { replace: true },
      );
    },
    [setParams, fallback],
  );
  return [range, setRange] as const;
}
