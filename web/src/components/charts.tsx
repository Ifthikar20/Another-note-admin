/**
 * Charts (Recharts), to one set of specs:
 *   - thin marks: 2px lines with a 10% wash under a lone series; bars at most 24px wide
 *     with a 4px rounded data end, square at the baseline, and a 2px gap between
 *     stacked segments; recessive, solid hairline grid;
 *   - colour follows the series (lib/series.ts), never its rank;
 *   - a legend whenever there are two or more series, and text always in text colours;
 *   - a tooltip on hover and keyboard focus whose value leads and whose series are keyed
 *     with a short line, never a box;
 *   - every chart has a table view with the same numbers, so nothing needs a hover.
 */
import { BarChart3, Table2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCompact, formatDay, formatDayLong, formatInt } from "@/lib/format";
import type { Series } from "@/lib/series";
import { cn } from "@/lib/utils";

type Row = Record<string, string | number | null>;
type Formatter = (value: number | null | undefined) => string;

const AXIS = { tickLine: false, axisLine: false, tickMargin: 6 } as const;

// --- the frame: title, legend, chart or table ----------------------------------------------
export function ChartCard({
  title,
  description,
  legend,
  legendMark = "rect",
  table,
  children,
  className,
  actions,
}: {
  title: string;
  description?: ReactNode;
  legend?: Series[];
  legendMark?: "rect" | "line";
  table: { columns: string[]; rows: (string | number)[][] };
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <section className={cn("rounded-lg border bg-card", className)}>
      <header className="flex flex-wrap items-start justify-between gap-2 px-4 pt-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{title}</h2>
          {description ? <p className="mt-0.5 text-xs text-muted-foreground">{description}</p> : null}
        </div>
        <div className="flex items-center gap-2">
          {actions}
          <div className="inline-flex rounded-md border p-0.5" role="group" aria-label={`${title}: chart or table`}>
            <ViewButton active={view === "chart"} onClick={() => setView("chart")} label="Chart">
              <BarChart3 className="size-3.5" />
            </ViewButton>
            <ViewButton active={view === "table"} onClick={() => setView("table")} label="Table">
              <Table2 className="size-3.5" />
            </ViewButton>
          </div>
        </div>
      </header>
      {legend && legend.length > 1 && view === "chart" ? <Legend series={legend} mark={legendMark} /> : null}
      <div className="px-2 pb-3 pt-2">{view === "chart" ? children : <DataView columns={table.columns} rows={table.rows} />}</div>
    </section>
  );
}

function ViewButton({ active, onClick, label, children }: { active: boolean; onClick: () => void; label: string; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={label}
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px]",
        active ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
      <span className="sr-only">{label}</span>
    </button>
  );
}

export function Legend({ series, mark = "rect" }: { series: Series[]; mark?: "rect" | "line" }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 px-4 pt-2 text-[12px] text-muted-foreground">
      {series.map((s) => (
        <li key={s.key} className="inline-flex items-center gap-1.5">
          <span
            aria-hidden
            className={mark === "rect" ? "size-2.5 rounded-[3px]" : "h-0.5 w-3 rounded-full"}
            style={{ background: s.color }}
          />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

function DataView({ columns, rows }: { columns: string[]; rows: (string | number)[][] }) {
  return (
    <div className="max-h-72 overflow-auto px-2">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((c, i) => (
              <TableHead key={c} className={i ? "text-right" : undefined}>
                {c}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, r) => (
            <TableRow key={r}>
              {row.map((cell, i) => (
                <TableCell key={i} className={cn("py-1.5", i ? "num text-right" : "whitespace-nowrap")}>
                  {cell}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// --- the tooltip -----------------------------------------------------------------------------
function ChartTooltip({
  active,
  payload,
  label,
  format,
  labelFormat,
  total,
}: TooltipProps<number, string> & { format: Formatter; labelFormat: (label: string) => string; total?: boolean }) {
  if (!active || !payload?.length) return null;
  const rows = payload.filter((p) => p.value !== undefined && p.value !== null);
  const sum = rows.reduce((acc, p) => acc + (Number(p.value) || 0), 0);
  return (
    <div className="min-w-40 rounded-md border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="mb-1 text-muted-foreground">{labelFormat(String(label))}</p>
      <ul className="space-y-0.5">
        {[...rows].reverse().map((p) => (
          <li key={String(p.dataKey)} className="flex items-center gap-2">
            <span aria-hidden className="h-0.5 w-3 shrink-0 rounded-full" style={{ background: p.color }} />
            <span className="num font-semibold">{format(Number(p.value))}</span>
            <span className="truncate text-muted-foreground">{p.name}</span>
          </li>
        ))}
      </ul>
      {total && rows.length > 1 ? (
        <p className="mt-1 flex items-center gap-2 border-t pt-1">
          <span className="num font-semibold">{format(sum)}</span>
          <span className="text-muted-foreground">Total</span>
        </p>
      ) : null}
    </div>
  );
}

// --- a stacked bar whose top segment ends round and whose segments sit 2px apart ---------------
interface ShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  fill?: string;
  payload?: Row;
}

// Recharts does not hand a custom shape its series key, so each series passes its own.
function segment(seriesKey: string) {
  return function SegmentShape(props: unknown) {
    return <Segment {...(props as ShapeProps)} seriesKey={seriesKey} />;
  };
}

function Segment({ x = 0, y = 0, width = 0, height = 0, fill, seriesKey, payload }: ShapeProps & { seriesKey: string }) {
  if (!height || height <= 0 || !width) return null;
  const top = payload?.__top === seriesKey;
  const bottom = payload?.__bottom === seriesKey;
  const gapTop = top ? 0 : 1;
  const gapBottom = bottom ? 0 : 1;
  const y0 = y + gapTop;
  const h = Math.max(0, height - gapTop - gapBottom);
  if (h <= 0) return null;
  const r = top ? Math.min(4, width / 2, h) : 0;
  const d = `M${x},${y0 + h} L${x},${y0 + r} Q${x},${y0} ${x + r},${y0} L${x + width - r},${y0} Q${x + width},${y0} ${x + width},${y0 + r} L${x + width},${y0 + h} Z`;
  return <path d={d} fill={fill} />;
}

/** Marks which series is the top and the bottom non-zero segment of each stack. */
function withEnds(rows: Row[], keys: string[]): Row[] {
  return rows.map((row) => {
    const present = keys.filter((k) => Number(row[k]) > 0);
    return { ...row, __top: present.at(-1) ?? null, __bottom: present[0] ?? null };
  });
}

// --- the charts --------------------------------------------------------------------------------
export function StackedBars({
  data,
  series,
  x = "day",
  format = formatInt,
  xFormat = formatDay,
  labelFormat = formatDayLong,
  height = 220,
}: {
  data: Row[];
  series: Series[];
  x?: string;
  format?: Formatter;
  xFormat?: (v: string) => string;
  labelFormat?: (v: string) => string;
  height?: number;
}) {
  const keys = series.map((s) => s.key);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={withEnds(data, keys)} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} accessibilityLayer>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={x} tickFormatter={xFormat} minTickGap={24} {...AXIS} />
        <YAxis tickFormatter={(v) => formatCompact(v)} width={44} allowDecimals={false} {...AXIS} />
        <Tooltip
          cursor={{ fill: "hsl(var(--muted))", opacity: 0.6 }}
          content={<ChartTooltip format={format} labelFormat={labelFormat} total />}
        />
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} stackId="stack" fill={s.color} maxBarSize={24} shape={segment(s.key)} isAnimationActive={false} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function SingleBars({
  data,
  dataKey,
  label,
  color,
  x = "day",
  format = formatInt,
  xFormat = formatDay,
  labelFormat = formatDayLong,
  height = 200,
  ticks,
}: {
  data: Row[];
  dataKey: string;
  label: string;
  color: string;
  x?: string;
  format?: Formatter;
  xFormat?: (v: string) => string;
  labelFormat?: (v: string) => string;
  height?: number;
  /** Where the axis labels go, when every point shouldn't be a candidate (hours: midnights). */
  ticks?: string[];
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={withEnds(data, [dataKey])} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} accessibilityLayer>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={x} tickFormatter={xFormat} minTickGap={24} ticks={ticks} interval={ticks ? 0 : "preserveEnd"} {...AXIS} />
        <YAxis tickFormatter={(v) => formatCompact(v)} width={44} allowDecimals={false} {...AXIS} />
        <Tooltip cursor={{ fill: "hsl(var(--muted))", opacity: 0.6 }} content={<ChartTooltip format={format} labelFormat={labelFormat} />} />
        <Bar dataKey={dataKey} name={label} fill={color} maxBarSize={24} shape={segment(dataKey)} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** One series over time: a 2px line, a 10% wash, and its latest value labelled at the end. */
export function TrendLine({
  data,
  dataKey,
  label,
  color,
  x = "day",
  format = formatInt,
  xFormat = formatDay,
  labelFormat = formatDayLong,
  height = 220,
}: {
  data: Row[];
  dataKey: string;
  label: string;
  color: string;
  x?: string;
  format?: Formatter;
  xFormat?: (v: string) => string;
  labelFormat?: (v: string) => string;
  height?: number;
}) {
  const last = data.length - 1;
  const gradient = `wash-${dataKey}`;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 16, right: 36, bottom: 0, left: 0 }} accessibilityLayer>
        <defs>
          <linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.12} />
            <stop offset="100%" stopColor={color} stopOpacity={0.04} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={x} tickFormatter={xFormat} minTickGap={24} {...AXIS} />
        <YAxis tickFormatter={(v) => formatCompact(v)} width={44} allowDecimals={false} {...AXIS} />
        <Tooltip
          cursor={{ stroke: "var(--viz-axis)", strokeWidth: 1 }}
          content={<ChartTooltip format={format} labelFormat={labelFormat} />}
        />
        <Area
          type="monotone"
          dataKey={dataKey}
          name={label}
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill={`url(#${gradient})`}
          isAnimationActive={false}
          activeDot={{ r: 4, stroke: "var(--viz-surface)", strokeWidth: 2, fill: color }}
          dot={(props: { cx?: number; cy?: number; index?: number; payload?: Row }) =>
            props.index === last && props.cx !== undefined && props.cy !== undefined ? (
              <g key="end">
                <circle cx={props.cx} cy={props.cy} r={4} fill={color} stroke="var(--viz-surface)" strokeWidth={2} />
                <text x={props.cx + 8} y={props.cy + 4} fontSize={11} fontWeight={600} fill="hsl(var(--foreground))">
                  {formatCompact(Number(props.payload?.[dataKey]))}
                </text>
              </g>
            ) : (
              <g key={props.index} />
            )
          }
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Several series stacked over time: each band edged with its own 2px line over a light wash. */
export function StackedArea({
  data,
  series,
  x = "day",
  format = formatInt,
  xFormat = formatDay,
  labelFormat = formatDayLong,
  yFormat = (v: number) => formatCompact(v),
  height = 220,
}: {
  data: Row[];
  series: Series[];
  x?: string;
  format?: Formatter;
  xFormat?: (v: string) => string;
  labelFormat?: (v: string) => string;
  yFormat?: (v: number) => string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} accessibilityLayer>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={x} tickFormatter={xFormat} minTickGap={24} {...AXIS} />
        <YAxis tickFormatter={yFormat} width={48} {...AXIS} />
        <Tooltip
          cursor={{ stroke: "var(--viz-axis)", strokeWidth: 1 }}
          content={<ChartTooltip format={format} labelFormat={labelFormat} total />}
        />
        {series.map((s) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stackId="stack"
            stroke={s.color}
            strokeWidth={2}
            fill={s.color}
            fillOpacity={0.14}
            isAnimationActive={false}
            activeDot={{ r: 4, stroke: "var(--viz-surface)", strokeWidth: 2, fill: s.color }}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

/**
 * Nominal categories ranked by one measure (cost by model, errors by reason): one series,
 * so one colour for every bar and no legend; the value is written at the bar's tip.
 */
export function RankedBars({
  items,
  color = "var(--viz-accent)",
  format = formatInt,
  max = 10,
}: {
  items: { key: string; label: string; value: number; hint?: string }[];
  color?: string;
  format?: Formatter;
  max?: number;
}) {
  const shown = items.slice(0, max);
  const top = Math.max(...shown.map((i) => i.value), 0) || 1;
  return (
    <ul className="space-y-2">
      {shown.map((item) => (
        <li key={item.key} className="grid grid-cols-[minmax(0,11rem)_1fr] items-center gap-3 text-[12px]">
          <span className="truncate text-muted-foreground" title={item.hint ?? item.label}>
            {item.label}
          </span>
          <span className="flex items-center gap-2">
            <span
              className="h-3 rounded-r-[4px]"
              style={{ width: `max(2px, ${(item.value / top) * 85}%)`, background: color }}
              aria-hidden
            />
            <span className="num whitespace-nowrap font-medium">{format(item.value)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Tiny daily counts inside a table row: muted bars, the latest day in the given colour. */
export function Sparkline({ values, color = "var(--viz-critical)", label }: { values: number[]; color?: string; label: string }) {
  const max = Math.max(...values, 1);
  const w = 3;
  const gap = 1;
  const h = 18;
  return (
    <svg width={values.length * (w + gap)} height={h} role="img" aria-label={label} className="block">
      {values.map((v, i) => {
        const bh = v > 0 ? Math.max(2, (v / max) * h) : 1;
        return <rect key={i} x={i * (w + gap)} y={h - bh} width={w} height={bh} rx={1} fill={i === values.length - 1 ? color : "var(--viz-other)"} opacity={v > 0 ? 1 : 0.35} />;
      })}
    </svg>
  );
}
