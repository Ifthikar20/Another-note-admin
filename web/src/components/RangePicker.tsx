/**
 * The date range: preset rows first (nobody fights a calendar for "last 30 days"), the
 * selection marked with a check, and a custom range below a hairline. Whole UTC days.
 */
import { CalendarDays, Check } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { PRESETS, rangeLabel, useRange, utcDay, type Preset } from "@/lib/range";
import { cn } from "@/lib/utils";

export function RangePicker({ fallback = "30d" }: { fallback?: Exclude<Preset, "custom"> }) {
  const [range, setRange] = useRange(fallback);
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(range.from);
  const [to, setTo] = useState(range.to);
  const presetLabel = PRESETS.find((p) => p.value === range.preset)?.label ?? "Custom";
  const valid = from && to && from <= to && to <= utcDay();
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setFrom(range.from);
          setTo(range.to);
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 gap-2 text-[13px]">
          <CalendarDays className="text-muted-foreground" />
          <span>{presetLabel}</span>
          <span className="text-muted-foreground">{rangeLabel(range)}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 p-1">
        <ul role="listbox" aria-label="Date range">
          {PRESETS.map((p) => (
            <li key={p.value}>
              <button
                type="button"
                role="option"
                aria-selected={range.preset === p.value}
                onClick={() => {
                  setRange({ preset: p.value });
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-[13px] hover:bg-muted"
              >
                <span className={cn(range.preset === p.value && "font-semibold")}>{p.label}</span>
                {range.preset === p.value ? <Check className="size-4" strokeWidth={3} /> : null}
              </button>
            </li>
          ))}
        </ul>
        <form
          className="mt-1 space-y-2 border-t px-2 pb-2 pt-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!valid) return;
            setRange({ from, to });
            setOpen(false);
          }}
        >
          <p className="text-[12px] font-medium text-muted-foreground">Custom range (UTC days)</p>
          <div className="flex items-center gap-1.5">
            <Input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} className="h-8 px-2 text-[12px]" aria-label="From" />
            <span className="text-muted-foreground">–</span>
            <Input type="date" value={to} min={from || undefined} max={utcDay()} onChange={(e) => setTo(e.target.value)} className="h-8 px-2 text-[12px]" aria-label="To" />
          </div>
          <Button type="submit" size="sm" className="h-7 w-full" disabled={!valid}>
            Apply
          </Button>
        </form>
      </PopoverContent>
    </Popover>
  );
}
