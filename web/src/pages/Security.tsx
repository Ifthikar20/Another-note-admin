/**
 * Security (6.4.8): failed sign-ins, PIN lockouts, refresh-token replays, and the networks
 * failures come from. Networks are shown only as a hash of their /24 (or /48) prefix: the
 * addresses themselves are never stored, and typed emails or PINs never are either.
 */
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { Pill } from "@/components/badges";
import { ChartCard, RankedBars, SingleBars } from "@/components/charts";
import { DataTable, LoadMore } from "@/components/DataTable";
import { FilterBar, SelectFilter } from "@/components/Filters";
import { PageHeader, Section } from "@/components/Page";
import { RangePicker } from "@/components/RangePicker";
import { StatGrid, StatTile } from "@/components/Stat";
import { EmptyState, ErrorState, LoadingBlock, QueryView } from "@/components/states";
import { RelativeTime } from "@/components/Time";
import { api } from "@/lib/api";
import { formatDateTime, formatDayOf, formatHour, formatInt, humanize } from "@/lib/format";
import { rangeLabel, useRange } from "@/lib/range";
import { CRITICAL } from "@/lib/series";
import type { AuthEvent, AuthKind, Page, SecuritySummary } from "@/lib/types";
import { cn } from "@/lib/utils";

import { AuthEventTable } from "./UserDetail";

/** Many failures across many different accounts from one network: someone trying a list. */
export function looksLikeStuffing(n: { failures: number; identifiers: number }): boolean {
  return n.failures >= 20 && n.identifiers >= 10;
}

const KINDS: { value: AuthKind; label: string }[] = [
  { value: "sign_in", label: "Sign-ins" },
  { value: "sign_in_failed", label: "Failed sign-ins" },
  { value: "pin_locked", label: "PIN lockouts" },
  { value: "pin_reset", label: "PIN resets" },
  { value: "refresh_replay", label: "Refresh replays" },
  { value: "sign_out", label: "Sign-outs" },
  { value: "sign_out_everywhere", label: "Signed out everywhere" },
  { value: "password_changed", label: "Password changes" },
  { value: "admin_action", label: "Admin actions" },
];

export default function Security() {
  const [range] = useRange("7d");
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind");
  const summary = useQuery({
    queryKey: ["security", "summary", { from: range.from, to: range.to }],
    queryFn: () => api.get<SecuritySummary>("/security/summary", { from: range.from, to: range.to }),
    placeholderData: keepPreviousData,
  });
  const events = useInfiniteQuery({
    queryKey: ["security", "events", { from: range.from, to: range.to, kind }],
    queryFn: ({ pageParam }) => api.get<Page<AuthEvent>>("/security/auth-events", { from: range.from, to: range.to, kind, cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
  });
  const rows = events.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div>
      <PageHeader title="Security" description={`Sign-in failures, lockouts and replays · ${rangeLabel(range)}. Times in your time zone.`} actions={<RangePicker fallback="7d" />} />
      <QueryView query={summary} loading={<LoadingBlock rows={6} />}>
        {(s) => {
          const hourly = s.failed_per_hour.map((h) => ({ hour: h.hour, failed: h.count }));
          // Over several days, one label a day, at the viewer's own midnight.
          const midnights = range.from === range.to ? undefined : hourly.filter((h) => new Date(h.hour).getHours() === 0).map((h) => h.hour);
          const suspicious = s.top_networks.filter(looksLikeStuffing);
          return (
            <div className="space-y-4">
              <StatGrid className="xl:grid-cols-6">
                <StatTile label="Sign-ins" value={formatInt(s.totals.sign_ins)} />
                <StatTile label="Failed sign-ins" value={formatInt(s.totals.failed)} />
                <StatTile label="PIN lockouts" value={formatInt(s.totals.lockouts)} />
                <StatTile label="Refresh replays" value={formatInt(s.totals.replays)} sub="Each ended every session" />
                <StatTile label="PIN resets" value={formatInt(s.totals.pin_resets)} />
                <StatTile label="Signed out everywhere" value={formatInt(s.totals.sign_outs_everywhere)} />
              </StatGrid>
              {suspicious.length ? (
                <div role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-[13px]">
                  <ShieldAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
                  <p>
                    <span className="font-semibold">Possible credential stuffing:</span> {formatInt(suspicious.length)} network{suspicious.length > 1 ? "s" : ""} tried many different
                    accounts. See the networks below. Sign-in rate limits apply to them; if they keep on, block the network at Cloudflare.
                  </p>
                </div>
              ) : null}
              <ChartCard
                title="Failed sign-ins per hour"
                description={range.from === range.to ? "Hours in your time zone" : "Each bar is an hour, in your time zone; hover for the exact hour"}
                table={{ columns: ["Hour", "Failed sign-ins"], rows: hourly.filter((h) => h.failed).map((h) => [formatDateTime(h.hour), formatInt(h.failed)]) }}
              >
                <SingleBars
                  data={hourly}
                  x="hour"
                  dataKey="failed"
                  label="Failed sign-ins"
                  color={CRITICAL}
                  xFormat={(v) => (range.from === range.to ? formatHour(v) : formatDayOf(v))}
                  ticks={midnights}
                  labelFormat={(v) => formatDateTime(v)}
                />
              </ChartCard>
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
                <Section title="Why sign-ins failed">
                  {s.failures_by_reason.length ? (
                    <RankedBars items={s.failures_by_reason.map((r) => ({ key: r.reason, label: humanize(r.reason), value: r.count }))} color={CRITICAL} />
                  ) : (
                    <EmptyState title="No failures" />
                  )}
                </Section>
                <Section title="Networks with the most failures" description="A hash of the network prefix; never an address." bodyClassName="p-0">
                  {s.top_networks.length ? (
                    <DataTable
                      label="Networks with the most failures"
                      rows={s.top_networks}
                      rowKey={(n) => n.ip_prefix_hash}
                      columns={[
                        { key: "net", header: "Network", cell: (n) => <code className="text-[12px]">{n.ip_prefix_hash.slice(0, 12)}</code> },
                        { key: "f", header: "Failures", numeric: true, cell: (n) => formatInt(n.failures) },
                        { key: "i", header: "Accounts tried", numeric: true, cell: (n) => formatInt(n.identifiers) },
                        { key: "c", header: "Countries", cell: (n) => n.countries.join(", ") || "—" },
                        { key: "l", header: "Last", cell: (n) => <RelativeTime iso={n.last_at} /> },
                        {
                          key: "flag",
                          header: "",
                          cell: (n) =>
                            looksLikeStuffing(n) ? (
                              <Pill variant="bad" title="Many failures across many different accounts">
                                <ShieldAlert className="mr-1 inline size-3" /> Stuffing?
                              </Pill>
                            ) : null,
                        },
                      ]}
                    />
                  ) : (
                    <EmptyState title="No failures in this range" />
                  )}
                </Section>
              </div>
            </div>
          );
        }}
      </QueryView>
      <Section title="Event stream" description="Newest first" className="mt-4" bodyClassName="p-0">
        <FilterBar className="mb-0 border-b px-3 py-2">
          <SelectFilter
            label="Kind"
            value={kind}
            onChange={(v) => setParams((p) => { const n = new URLSearchParams(p); if (v) n.set("kind", v); else n.delete("kind"); return n; }, { replace: true })}
            options={KINDS}
          />
        </FilterBar>
        {events.isPending ? (
          <LoadingBlock className="p-3" />
        ) : events.isError && !events.data ? (
          <ErrorState error={events.error} onRetry={() => void events.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title="No events match" />
        ) : (
          <div className={cn("transition-opacity", events.isFetching && events.isPlaceholderData && "opacity-60")}>
            <AuthEventTable rows={rows} />
            <LoadMore hasMore={!!events.hasNextPage} loading={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()} shown={rows.length} />
          </div>
        )}
      </Section>
    </div>
  );
}
