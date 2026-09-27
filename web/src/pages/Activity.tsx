/**
 * Activity: what people do in the app, and what went wrong for them.
 *
 * From the student app's own analytics (page views, a few key actions, and every error),
 * through admin_analytics_v: an event's kind, its name (an error's message, at most 160
 * characters), the page, and the three utm_* tags. Never an error's stack, the browser's
 * user agent, its random ids, or any other link tag. Totals and grouped errors are for
 * every role; the event-by-event log, which says who did what, is for support and owners.
 */
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ChartCard, SingleBars, Sparkline, StackedBars } from "@/components/charts";
import { DataTable, LoadMore } from "@/components/DataTable";
import { FilterBar, SearchBox, SelectFilter } from "@/components/Filters";
import { PageHeader, Section } from "@/components/Page";
import { RangePicker } from "@/components/RangePicker";
import { StatGrid, StatTile } from "@/components/Stat";
import { EmptyState, ErrorState, LoadingBlock, QueryView } from "@/components/states";
import { RelativeTime } from "@/components/Time";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { formatInt } from "@/lib/format";
import { useCan } from "@/lib/me";
import { pivot, tableOf } from "@/lib/pivot";
import { daysBetween, rangeLabel, useRange } from "@/lib/range";
import { CRITICAL } from "@/lib/series";
import type { AnalyticsEvent, AnalyticsSummary, ErrorGroup, ErrorGroups, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

import { EventTable, Segmented } from "./UserDetail";

const KIND_SERIES = [
  { key: "view", label: "Page views", color: "var(--viz-1)" },
  { key: "action", label: "Actions", color: "var(--viz-2)" },
];

export default function ActivityPage() {
  const [range] = useRange("7d");
  const [params, setParams] = useSearchParams();
  const canLog = useCan("activity.read");
  const tab = params.get("tab") ?? "overview";
  const setTab = (next: string, extra: Record<string, string | null> = {}) =>
    setParams(
      (current) => {
        const n = new URLSearchParams(current);
        n.set("tab", next);
        for (const [k, v] of Object.entries(extra)) {
          if (v) n.set(k, v);
          else n.delete(k);
        }
        return n;
      },
      { replace: true },
    );

  return (
    <div>
      <PageHeader
        title="Activity"
        description={`What people do in the app, and what went wrong · ${rangeLabel(range)}, UTC days. Never what anyone wrote or studied.`}
        actions={<RangePicker fallback="7d" />}
      />
      <Tabs value={tab} onValueChange={(v) => setTab(v)}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="errors">What went wrong</TabsTrigger>
          {canLog ? <TabsTrigger value="log">Event log</TabsTrigger> : null}
        </TabsList>
        <TabsContent value="overview" className="mt-4">
          <Overview from={range.from} to={range.to} />
        </TabsContent>
        <TabsContent value="errors" className="mt-4">
          <Errors from={range.from} to={range.to} onOpen={canLog ? (name) => setTab("log", { kind: "error", name }) : undefined} />
        </TabsContent>
        {canLog ? (
          <TabsContent value="log" className="mt-4">
            <Log from={range.from} to={range.to} />
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}

function Overview({ from, to }: { from: string; to: string }) {
  const summary = useQuery({
    queryKey: ["analytics", "summary", { from, to }],
    queryFn: () => api.get<AnalyticsSummary>("/analytics/summary", { from, to }),
    placeholderData: keepPreviousData,
  });
  const days = useMemo(() => daysBetween(from, to), [from, to]);
  return (
    <QueryView query={summary} loading={<LoadingBlock rows={6} />}>
      {(s) => {
        const rows = pivot(
          days,
          s.by_day.flatMap((d) => [
            { day: d.day, key: "view", value: d.view },
            { day: d.day, key: "action", value: d.action },
          ]),
        );
        const errors = s.by_day.map((d) => ({ day: d.day, errors: d.error }));
        return (
          <div className="space-y-4">
            <StatGrid>
              <StatTile label="Page views" value={formatInt(s.totals.views)} />
              <StatTile label="Actions" value={formatInt(s.totals.actions)} sub="Teach mode, new sessions, quizzes…" />
              <StatTile label="Errors" value={formatInt(s.totals.errors)} sub="Grouped under What went wrong" />
              <StatTile label="People" value={formatInt(s.totals.users)} sub="Signed in, with any event" />
            </StatGrid>
            <div className="grid gap-4 xl:grid-cols-2">
              <ChartCard title="Page views and actions per day" description="UTC days" legend={KIND_SERIES} table={tableOf(rows, KIND_SERIES, formatInt)}>
                <StackedBars data={rows} series={KIND_SERIES} />
              </ChartCard>
              <ChartCard
                title="Errors per day"
                description="Errors people hit in the app · UTC days"
                table={{ columns: ["Day (UTC)", "Errors"], rows: errors.map((e) => [e.day, formatInt(e.errors)]) }}
              >
                <SingleBars data={errors} dataKey="errors" label="Errors" color={CRITICAL} />
              </ChartCard>
            </div>
            <div className="grid gap-4 xl:grid-cols-3">
              <NameCounts title="Pages opened" rows={s.top_pages} unit="Views" />
              <NameCounts title="Actions taken" rows={s.top_actions} unit="Times" />
              <Section title="Where people came from" description="Link tags (utm_*) only" bodyClassName="p-0">
                {s.campaigns.length ? (
                  <DataTable
                    label="Where people came from"
                    rows={s.campaigns}
                    rowKey={(c) => `${c.utm_source}/${c.utm_medium}/${c.utm_campaign}`}
                    columns={[
                      { key: "c", header: "Source / medium / campaign", cell: (c) => [c.utm_source, c.utm_medium, c.utm_campaign].filter(Boolean).join(" / ") },
                      { key: "e", header: "Events", numeric: true, cell: (c) => formatInt(c.events) },
                      { key: "u", header: "People", numeric: true, cell: (c) => formatInt(c.users) },
                    ]}
                  />
                ) : (
                  <EmptyState title="No tagged links in this range" />
                )}
              </Section>
            </div>
          </div>
        );
      }}
    </QueryView>
  );
}

function NameCounts({ title, rows, unit }: { title: string; rows: { name: string; count: number; users: number }[]; unit: string }) {
  return (
    <Section title={title} bodyClassName="p-0">
      {rows.length ? (
        <DataTable
          label={title}
          rows={rows}
          rowKey={(r) => r.name}
          columns={[
            { key: "n", header: "Name", cell: (r) => <span className="block max-w-[14rem] truncate" title={r.name}>{r.name}</span> },
            { key: "c", header: unit, numeric: true, cell: (r) => formatInt(r.count) },
            { key: "u", header: "People", numeric: true, cell: (r) => formatInt(r.users) },
          ]}
        />
      ) : (
        <EmptyState title="Nothing in this range" />
      )}
    </Section>
  );
}

type ErrorSort = "latest" | "count" | "users";

function Errors({ from, to, onOpen }: { from: string; to: string; onOpen?: (name: string) => void }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<ErrorSort>("latest");
  const errors = useInfiniteQuery({
    queryKey: ["analytics", "errors", { from, to, q }],
    queryFn: ({ pageParam }) => api.get<ErrorGroups>("/analytics/errors", { from, to, q, cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
  });
  const days = useMemo(() => daysBetween(from, to), [from, to]);
  const loaded = errors.data?.pages.flatMap((p) => p.items) ?? [];
  // The admin API sends the most recent first; the other orders sort what has loaded.
  const rows = sort === "latest" ? loaded : [...loaded].sort((a, b) => (sort === "count" ? b.count - a.count : b.users - a.users));
  const trend = (g: ErrorGroup) => {
    const by = new Map(g.by_day.map((d) => [d.day, d.count]));
    return days.map((d) => by.get(d) ?? 0);
  };
  return (
    <div>
      <FilterBar>
        <SearchBox value={q} onSearch={setQ} placeholder="Words in the error" label="Search errors" />
        <Segmented
          value={sort}
          onChange={setSort}
          label="Order"
          options={[
            { value: "latest", label: "Latest" },
            { value: "count", label: "Most often" },
            { value: "users", label: "Most people" },
          ]}
        />
        <p className="text-[12px] text-muted-foreground">Grouped by message. The message is all that is kept of an error: never its stack.</p>
      </FilterBar>
      <div className="rounded-lg border bg-card">
        {errors.isPending ? (
          <LoadingBlock className="p-3" />
        ) : errors.isError && !errors.data ? (
          <ErrorState error={errors.error} onRetry={() => void errors.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title="Nothing went wrong in this range" />
        ) : (
          <div className={cn("transition-opacity", errors.isFetching && errors.isPlaceholderData && "opacity-60")}>
            <DataTable
              label="What went wrong"
              rows={rows}
              rowKey={(g) => g.name}
              onRowClick={onOpen ? (g) => onOpen(g.name) : undefined}
              columns={[
                { key: "name", header: "Error", cell: (g) => <span className="block max-w-xl break-words font-mono text-[12px]">{g.name}</span> },
                { key: "count", header: "Times", numeric: true, cell: (g) => formatInt(g.count) },
                { key: "users", header: "People", numeric: true, cell: (g) => formatInt(g.users) },
                {
                  key: "trend",
                  header: "Per day",
                  cell: (g) => <Sparkline values={trend(g)} label={`${g.count} times over the range; ${trend(g).at(-1) ?? 0} on the last day`} />,
                },
                { key: "paths", header: "Pages", cell: (g) => <span className="block max-w-[14rem] truncate text-muted-foreground" title={g.paths.join("\n")}>{g.paths.join(", ") || "—"}</span> },
                { key: "last", header: "Last seen", cell: (g) => <RelativeTime iso={g.last_at} /> },
                { key: "first", header: "First seen", cell: (g) => <RelativeTime iso={g.first_at} /> },
              ]}
            />
            <LoadMore hasMore={!!errors.hasNextPage} loading={errors.isFetchingNextPage} onClick={() => void errors.fetchNextPage()} shown={rows.length} />
          </div>
        )}
      </div>
      {onOpen ? <p className="mt-2 text-[12px] text-muted-foreground">Open an error to see each time it happened, and to whom.</p> : null}
    </div>
  );
}

function Log({ from, to }: { from: string; to: string }) {
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind");
  const name = params.get("name");
  const path = params.get("path");
  const userId = params.get("user");
  const [userDraft, setUserDraft] = useState(userId ?? "");
  const set = (key: string, value: string | null) =>
    setParams(
      (current) => {
        const n = new URLSearchParams(current);
        if (value) n.set(key, value);
        else n.delete(key);
        return n;
      },
      { replace: true },
    );
  const events = useInfiniteQuery({
    queryKey: ["analytics", "events", { from, to, kind, name, path, userId }],
    queryFn: ({ pageParam }) =>
      api.get<Page<AnalyticsEvent>>("/analytics/events", { from, to, kind, name, path, user_id: userId, cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
  });
  const rows = events.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div>
      <FilterBar>
        <SelectFilter
          label="Kind"
          value={kind}
          onChange={(v) => set("kind", v)}
          options={[
            { value: "view", label: "Page views" },
            { value: "action", label: "Actions" },
            { value: "error", label: "Errors" },
          ]}
        />
        <SearchBox value={path ?? ""} onSearch={(v) => set("path", v || null)} placeholder="Page, e.g. /dashboard/note" label="Page starts with" className="[&_input]:w-56" />
        <form
          className="flex items-center gap-1"
          onSubmit={(e) => {
            e.preventDefault();
            set("user", /^\d+$/.test(userDraft.trim()) ? userDraft.trim() : null);
          }}
        >
          <Input value={userDraft} onChange={(e) => setUserDraft(e.target.value)} placeholder="Account id" aria-label="Account id" className="h-8 w-28 text-[13px]" inputMode="numeric" />
          <Button type="submit" variant="outline" size="sm" className="h-8">
            Filter
          </Button>
        </form>
        {name ? (
          <Button variant="secondary" size="sm" className="h-8 max-w-md" onClick={() => set("name", null)} title="Show every event">
            <span className="truncate font-mono text-[12px]">{name}</span> ✕
          </Button>
        ) : null}
      </FilterBar>
      <div className="rounded-lg border bg-card">
        {events.isPending ? (
          <LoadingBlock className="p-3" />
        ) : events.isError && !events.data ? (
          <ErrorState error={events.error} onRetry={() => void events.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title="No events match" />
        ) : (
          <div className={cn("transition-opacity", events.isFetching && events.isPlaceholderData && "opacity-60")}>
            <EventTable rows={rows} />
            <LoadMore hasMore={!!events.hasNextPage} loading={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()} shown={rows.length} />
          </div>
        )}
      </div>
    </div>
  );
}
