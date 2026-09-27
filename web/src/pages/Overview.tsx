/**
 * Overview (6.4.1): who is here, who signs in, what it costs, and what is waiting, today
 * and now; the trends below cover the chosen range, in UTC days.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { ChartCard, StackedArea, StackedBars, TrendLine } from "@/components/charts";
import { DataTable } from "@/components/DataTable";
import { PageHeader, Section } from "@/components/Page";
import { RangePicker } from "@/components/RangePicker";
import { BudgetMeter, StatGrid, StatTile } from "@/components/Stat";
import { ErrorState, LoadingBlock, QueryView } from "@/components/states";
import { api } from "@/lib/api";
import {
  formatBytes,
  formatCompact,
  formatHours,
  formatInt,
  formatMoney,
  formatMoneyCompact,
  formatRelative,
} from "@/lib/format";
import { pivot, present, tableOf } from "@/lib/pivot";
import { daysBetween, rangeLabel, useRange, utcDay } from "@/lib/range";
import { ACCENT, FEATURE_AREAS, METHODS, OTHER, PROVIDERS, areaOf, featureLabel } from "@/lib/series";
import type { ActiveUsers, AnalyticsSummary, Overview as OverviewT, SignIns, UsageSummary } from "@/lib/types";

export default function Overview() {
  const [range] = useRange("30d");
  const q = { from: range.from, to: range.to };
  const today = utcDay();
  const live = { placeholderData: keepPreviousData, refetchInterval: 60_000 } as const;

  const overview = useQuery({ queryKey: ["overview", q], queryFn: () => api.get<OverviewT>("/overview", q), ...live });
  const dau = useQuery({ queryKey: ["metrics", "active-users", q], queryFn: () => api.get<ActiveUsers>("/metrics/active-users", q), ...live });
  const signIns = useQuery({ queryKey: ["metrics", "sign-ins", q], queryFn: () => api.get<SignIns>("/metrics/sign-ins", q), ...live });
  const byFeature = useQuery({
    queryKey: ["usage", "summary", "feature", q],
    queryFn: () => api.get<UsageSummary>("/usage/summary", { ...q, group: "feature" }),
    placeholderData: keepPreviousData,
  });
  const byProvider = useQuery({
    queryKey: ["usage", "summary", "provider", q],
    queryFn: () => api.get<UsageSummary>("/usage/summary", { ...q, group: "provider" }),
    placeholderData: keepPreviousData,
  });
  const errorsToday = useQuery({
    queryKey: ["analytics", "summary", { from: today, to: today }],
    queryFn: () => api.get<AnalyticsSummary>("/analytics/summary", { from: today, to: today }),
    ...live,
  });

  const days = useMemo(() => daysBetween(range.from, range.to), [range.from, range.to]);

  return (
    <div>
      <PageHeader
        title="Overview"
        description={
          <>
            Today and right now; trends for {rangeLabel(range)} in UTC days.
            {overview.data ? <> Updated {formatRelative(overview.data.generated_at)}.</> : null}
          </>
        }
        actions={<RangePicker />}
      />

      <QueryView query={overview} loading={<LoadingBlock rows={4} />}>
        {(o) => (
          <StatGrid className="mb-4">
            <StatTile
              label="Accounts"
              value={formatInt(o.accounts.total)}
              sub={`${formatInt(o.accounts.adults)} standard · ${formatInt(o.accounts.children)} child profiles`}
              to="/users"
            />
            <StatTile
              label="Online now"
              value={formatInt(o.activity.online_now)}
              sub={`${formatInt(o.sessions.live)} live sessions for ${formatInt(o.sessions.users_with_live_sessions)} people`}
            />
            <StatTile
              label="Active today"
              value={formatInt(o.activity.active_today)}
              sub={`${formatInt(o.activity.active_7d)} in 7 days · ${formatInt(o.activity.active_30d)} in 30 days`}
            />
            <StatTile
              label="Sign-ins today"
              value={formatInt(o.sign_ins.today)}
              sub={`${formatInt(o.sign_ins.failed_today)} failed`}
              to="/security"
            />
            <StatTile label="AI cost today" value={formatMoney(o.usage.cost_today_usd)} sub={`${formatCompact(o.usage.tokens_today)} tokens`} to="/usage" />
            <StatTile label="AI cost this month" value={formatMoneyCompact(o.usage.cost_month_usd)} to="/usage?range=mtd">
              <BudgetMeter spent={o.usage.cost_month_usd} budget={o.usage.budget_month_usd} />
            </StatTile>
            <StatTile
              label="Open tickets"
              value={formatInt(o.tickets.open + o.tickets.waiting_on_us)}
              sub={`${formatInt(o.tickets.open)} new · ${formatInt(o.tickets.waiting_on_us)} waiting on us${o.tickets.oldest_open_hours !== null ? ` · oldest ${formatHours(o.tickets.oldest_open_hours)}` : ""}`}
              to="/tickets"
            />
            <StatTile
              label="App errors today"
              value={errorsToday.data ? formatInt(errorsToday.data.totals.errors) : "—"}
              sub={errorsToday.data ? `${formatInt(errorsToday.data.totals.users)} people used the app today` : "What went wrong, grouped"}
              to="/activity?tab=errors&range=today"
            />
          </StatGrid>
        )}
      </QueryView>

      <div className="grid gap-4 xl:grid-cols-2">
        <DauChart query={dau} />
        <SignInChart query={signIns} days={days} />
        <CostByAreaChart query={byFeature} days={days} />
        <TokensByProviderChart query={byProvider} days={days} />
      </div>

      <QueryView query={overview} loading={null}>
        {(o) => (
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Section title="Top features this month" description="By cost; the tokens are input plus output." bodyClassName="p-0">
              <DataTable
                label="Top features this month"
                rows={o.usage.top_features_month}
                rowKey={(r) => r.feature}
                columns={[
                  { key: "f", header: "Feature", cell: (r) => featureLabel(r.feature) },
                  // Voice is billed by the character and transcription by the minute: no tokens.
                  { key: "t", header: "Tokens", numeric: true, cell: (r) => (r.tokens ? formatInt(r.tokens) : "—") },
                  { key: "c", header: "Cost", numeric: true, cell: (r) => formatMoney(r.cost_usd) },
                ]}
              />
            </Section>
            <Section title="Storage" description="What people keep in AnotherNote: counts and sizes only.">
              <p className="text-2xl font-semibold">{formatBytes(o.storage.pdf_bytes)}</p>
              <p className="text-[13px] text-muted-foreground">in {formatInt(o.storage.pdfs)} PDFs</p>
              <p className="mt-3 text-[12px] text-muted-foreground">
                Sign-in and usage history start on the day metering was deployed; there is nothing before it to show. <Link to="/usage" className="underline">Usage and cost</Link>
              </p>
            </Section>
          </div>
        )}
      </QueryView>
    </div>
  );
}

type Q<T> = ReturnType<typeof useQuery<T>>;

function Frame<T>({ query, title, children }: { query: Q<T>; title: string; children: (data: T) => React.ReactNode }) {
  if (query.isPending) return <section className="rounded-lg border p-4"><p className="text-sm font-semibold">{title}</p><LoadingBlock rows={6} /></section>;
  if (query.isError && !query.data) return <section className="rounded-lg border"><ErrorState error={query.error} onRetry={() => void query.refetch()} /></section>;
  return <div className={query.isFetching && query.isPlaceholderData ? "opacity-60 transition-opacity" : "transition-opacity"}>{children(query.data as T)}</div>;
}

function DauChart({ query }: { query: Q<ActiveUsers> }) {
  return (
    <Frame query={query} title="Daily active users">
      {(d) => {
        const rows = d.series.map((p) => ({ day: p.day, dau: p.dau }));
        return (
          <ChartCard
            title="Daily active users"
            description={`People with any active time that UTC day · ${formatInt(d.wau)} in the last 7 days, ${formatInt(d.mau)} in 30`}
            table={tableOf(rows, [{ key: "dau", label: "Active users", color: ACCENT }], formatInt)}
          >
            <TrendLine data={rows} dataKey="dau" label="Active users" color={ACCENT} />
          </ChartCard>
        );
      }}
    </Frame>
  );
}

function SignInChart({ query, days }: { query: Q<SignIns>; days: string[] }) {
  return (
    <Frame query={query} title="Sign-ins by method">
      {(d) => {
        const rows = pivot(days, d.series.map((p) => ({ day: p.day, key: p.method, value: p.count })));
        const series = present(METHODS, rows);
        return (
          <ChartCard
            title="Sign-ins by method"
            description={`${formatInt(d.totals.sign_ins)} sign-ins and ${formatInt(d.totals.failures)} failed attempts · UTC days`}
            legend={series}
            table={tableOf(rows, series, formatInt)}
          >
            <StackedBars data={rows} series={series} />
          </ChartCard>
        );
      }}
    </Frame>
  );
}

function CostByAreaChart({ query, days }: { query: Q<UsageSummary>; days: string[] }) {
  return (
    <Frame query={query} title="Cost by feature">
      {(d) => {
        const priced = d.totals.cost_usd !== null;
        const rows = pivot(
          days,
          d.series.map((p) => ({ day: p.day, key: p.key, value: priced ? p.cost_usd : p.tokens })),
          (feature) => areaOf(feature).key,
        );
        const series = present([...FEATURE_AREAS, OTHER], rows);
        const format = priced ? formatMoney : formatInt;
        return (
          <ChartCard
            title={priced ? "Cost by feature" : "Tokens by feature"}
            description={
              priced
                ? `${formatMoney(d.totals.cost_usd)} in the range · UTC days${d.totals.unpriced_calls ? ` · ${formatInt(d.totals.unpriced_calls)} calls have no price yet` : ""}`
                : "No prices are set yet, so this shows tokens · UTC days"
            }
            legend={series}
            table={tableOf(rows, series, format)}
          >
            <StackedArea data={rows} series={series} format={format} yFormat={priced ? (v) => `$${formatCompact(v)}` : (v) => formatCompact(v)} />
          </ChartCard>
        );
      }}
    </Frame>
  );
}

function TokensByProviderChart({ query, days }: { query: Q<UsageSummary>; days: string[] }) {
  return (
    <Frame query={query} title="Tokens by provider">
      {(d) => {
        const rows = pivot(days, d.series.map((p) => ({ day: p.day, key: p.key, value: p.tokens })));
        const series = present(PROVIDERS, rows);
        return (
          <ChartCard
            title="Tokens by provider"
            description="Input plus output tokens of AI calls · UTC days"
            legend={series}
            table={tableOf(rows, series, formatInt)}
          >
            <StackedBars data={rows} series={series} format={formatInt} />
          </ChartCard>
        );
      }}
    </Frame>
  );
}
