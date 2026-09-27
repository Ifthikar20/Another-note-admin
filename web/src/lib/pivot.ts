/** Long rows (day, key, value) into wide chart rows ({day, a, b, ...}), one per day. */
import { formatDay } from "./format";
import type { Series } from "./series";

export type WideRow = Record<string, string | number | null>;

export function pivot(
  days: string[],
  points: { day: string; key: string; value: number | null }[],
  keyOf: (key: string) => string = (k) => k,
): WideRow[] {
  const byDay = new Map<string, WideRow>(days.map((d) => [d, { day: d }]));
  for (const p of points) {
    const row = byDay.get(p.day);
    if (!row) continue;
    const k = keyOf(p.key);
    row[k] = (Number(row[k]) || 0) + (p.value ?? 0);
  }
  return [...byDay.values()];
}

/** The keys of `series` that have any value in `rows`, in the series' fixed order. */
export function present(series: Series[], rows: WideRow[]): Series[] {
  return series.filter((s) => rows.some((r) => Number(r[s.key]) > 0));
}

/** A chart's table view: one row per day, one column per series, and the total. */
export function tableOf(rows: WideRow[], series: Series[], format: (n: number) => string): { columns: string[]; rows: (string | number)[][] } {
  return {
    columns: ["Day (UTC)", ...series.map((s) => s.label), ...(series.length > 1 ? ["Total"] : [])],
    rows: rows.map((r) => {
      const values = series.map((s) => Number(r[s.key]) || 0);
      return [formatDay(String(r.day)), ...values.map(format), ...(series.length > 1 ? [format(values.reduce((a, b) => a + b, 0))] : [])];
    }),
  };
}
