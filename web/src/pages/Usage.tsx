/**
 * Usage and cost (6.4.5): tokens, voice characters and transcription minutes by feature,
 * provider, model or day; who uses the most; and days far above someone's usual.
 * Cost is units times the price in force when each call was made; a call whose price was
 * not set yet counts in the units but not the cost, and says so.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ChartCard, SingleBars } from "@/components/charts";
import { DataTable } from "@/components/DataTable";
import { SelectFilter } from "@/components/Filters";
import { Identity } from "@/components/Identity";
import { PageHeader, Section } from "@/components/Page";
import { RangePicker } from "@/components/RangePicker";
import { BudgetMeter, StatGrid, StatTile } from "@/components/Stat";
import { EmptyState, LoadingBlock, QueryView } from "@/components/states";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatAudioMinutes, formatCompact, formatDayLong, formatInt, formatMoney, formatMoneyCompact } from "@/lib/format";
import { addDays, daysBetween, rangeLabel, useRange, utcDay } from "@/lib/range";
import { ACCENT } from "@/lib/series";
import type { Anomalies, TopUsers, UsageGroup, UsageSummary } from "@/lib/types";

import { Segmented, UsageTable } from "./UserDetail";

const GROUPS: { value: UsageGroup; label: string }[] = [
  { value: "feature", label: "Feature" },
  { value: "provider", label: "Provider" },
  { value: "model", label: "Model" },
  { value: "day", label: "Day" },
];

export default function Usage() {
  const [range] = useRange("30d");
  const [params, setParams] = useSearchParams();
  const group = (params.get("group") as UsageGroup | null) ?? "feature";
  const setGroup = (g: UsageGroup) =>
    setParams((p) => { const n = new URLSearchParams(p); if (g === "feature") n.delete("group"); else n.set("group", g); return n; }, { replace: true });
  const summary = useQuery({
    queryKey: ["usage", "summary", group, { from: range.from, to: range.to }],
    queryFn: () => api.get<UsageSummary>("/usage/summary", { from: range.from, to: range.to, group }),
    placeholderData: keepPreviousData,
  });
  const days = useMemo(() => daysBetween(range.from, range.to), [range.from, range.to]);

  return (
    <div>
      <PageHeader
        title="Usage and cost"
        description={`AI tokens, voice and transcription, and what they cost · ${rangeLabel(range)}, UTC days`}
        actions={
          <>
            <Segmented value={group} onChange={setGroup} options={GROUPS} label="Group by" />
            <RangePicker />
          </>
        }
      />
      <QueryView query={summary} loading={<LoadingBlock rows={8} />}>
        {(s) => {
          const priced = s.totals.cost_usd !== null;
          const mtd = s.month_to_date;
          return (
            <div className="space-y-4">
              <StatGrid>
                <StatTile label="AI cost in the range" value={formatMoneyCompact(s.totals.cost_usd)} sub={s.totals.unpriced_calls ? `${formatInt(s.totals.unpriced_calls)} calls have no price yet` : `${formatInt(s.totals.calls)} calls, all priced`} />
                <StatTile label={mtd ? `This month (${mtd.month})` : "This month"} value={formatMoneyCompact(mtd?.cost_usd ?? null)}>
                  <BudgetMeter spent={mtd?.cost_usd ?? null} budget={mtd?.budget_usd ?? null} />
                </StatTile>
                <StatTile
                  label="AI tokens"
                  value={formatCompact(s.totals.input_tokens + s.totals.output_tokens)}
                  sub={`${formatCompact(s.totals.input_tokens)} in · ${formatCompact(s.totals.output_tokens)} out · ${formatCompact(s.totals.cache_read_tokens)} from cache`}
                />
                <StatTile label="Voice and transcription" value={`${formatCompact(s.totals.characters)} chars`} sub={`${formatAudioMinutes(s.totals.audio_ms)} of audio transcribed`} />
              </StatGrid>
              {group === "day" ? (
                <ChartCard
                  title={priced ? "Cost per day" : "Tokens per day"}
                  description={priced ? "UTC days" : "No prices set yet, so this shows tokens · UTC days"}
                  table={{
                    columns: ["Day (UTC)", "Calls", "Tokens", "Characters", "Cost"],
                    rows: s.rows.map((r) => [r.key, formatInt(r.calls), formatInt(r.input_tokens + r.output_tokens), formatInt(r.characters), formatMoney(r.cost_usd)]),
                  }}
                >
                  <SingleBars
                    data={days.map((day) => {
                      const r = s.rows.find((x) => x.key === day);
                      return { day, value: r ? (priced ? r.cost_usd ?? 0 : r.input_tokens + r.output_tokens) : 0 };
                    })}
                    dataKey="value"
                    label={priced ? "Cost" : "Tokens"}
                    color={ACCENT}
                    format={priced ? formatMoney : formatInt}
                  />
                </ChartCard>
              ) : (
                <UsageTable summary={s} group={group} />
              )}
            </div>
          );
        }}
      </QueryView>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <TopUsersSection from={range.from} to={range.to} />
        <AnomaliesSection />
      </div>
    </div>
  );
}

function TopUsersSection({ from, to }: { from: string; to: string }) {
  const [metric, setMetric] = useState<"cost" | "tokens" | "characters">("cost");
  const top = useQuery({
    queryKey: ["usage", "top-users", metric, { from, to }],
    queryFn: () => api.get<TopUsers>("/usage/top-users", { from, to, metric, limit: 20 }),
    placeholderData: keepPreviousData,
  });
  return (
    <Section
      title="Who uses the most"
      description="Masked. Open a person for the detail."
      actions={
        <SelectFilter
          label="By"
          value={metric === "cost" ? null : metric}
          allLabel="Cost"
          onChange={(v) => setMetric((v as typeof metric) ?? "cost")}
          options={[
            { value: "tokens", label: "Tokens" },
            { value: "characters", label: "Voice characters" },
          ]}
        />
      }
      bodyClassName="p-0"
    >
      <QueryView query={top} isEmpty={(t) => !t.items.length} empty={<EmptyState title="No usage in this range" />}>
        {(t) => (
          <DataTable
            label="Who uses the most"
            rows={t.items}
            rowKey={(r) => r.user.id}
            columns={[
              { key: "rank", header: "#", numeric: true, cell: (r) => t.items.indexOf(r) + 1 },
              { key: "who", header: "Person", cell: (r) => <Identity id={r.user.id} identity={r.user.identity} kind={r.user.kind} className="max-w-[14rem]" /> },
              { key: "calls", header: "Calls", numeric: true, cell: (r) => formatInt(r.calls) },
              { key: "tokens", header: "Tokens", numeric: true, cell: (r) => formatCompact(r.tokens) },
              { key: "chars", header: "Characters", numeric: true, cell: (r) => formatCompact(r.characters) },
              { key: "cost", header: "Cost", numeric: true, cell: (r) => formatMoney(r.cost_usd) },
            ]}
          />
        )}
      </QueryView>
    </Section>
  );
}

function AnomaliesSection() {
  const [day, setDay] = useState(() => addDays(utcDay(), -1));
  const anomalies = useQuery({
    queryKey: ["usage", "anomalies", day],
    queryFn: () => api.get<Anomalies>("/usage/anomalies", { date: day }),
    placeholderData: keepPreviousData,
  });
  return (
    <Section
      title="Unusual days"
      description="People whose day was more than 5 times their usual (their 30-day median), or over their plan's share."
      actions={<Input type="date" value={day} max={utcDay()} onChange={(e) => e.target.value && setDay(e.target.value)} className="h-8 w-40 text-[12px]" aria-label="Day (UTC)" />}
      bodyClassName="p-0"
    >
      <QueryView query={anomalies} isEmpty={(a) => !a.items.length} empty={<EmptyState title={`Nothing unusual on ${formatDayLong(day)}`} />}>
        {(a) => (
          <DataTable
            label="Unusual days"
            rows={a.items}
            rowKey={(r) => `${r.user.id}-${r.metric}`}
            columns={[
              { key: "who", header: "Person", cell: (r) => <Identity id={r.user.id} identity={r.user.identity} kind={r.user.kind} className="max-w-[14rem]" /> },
              { key: "value", header: "That day", numeric: true, cell: (r) => (r.metric === "cost" ? formatMoney(r.value) : formatCompact(r.value)) },
              { key: "median", header: "Usual", numeric: true, cell: (r) => (r.metric === "cost" ? formatMoney(r.median_30d) : formatCompact(r.median_30d)) },
              { key: "ratio", header: "Times usual", numeric: true, cell: (r) => (r.ratio ? `${r.ratio}×` : "—") },
              { key: "why", header: "Why", cell: (r) => (r.reason === "spike" ? "Spike" : "Over plan share") },
              { key: "plan", header: "Plan", cell: (r) => r.plan_id ?? "—" },
            ]}
          />
        )}
      </QueryView>
    </Section>
  );
}
