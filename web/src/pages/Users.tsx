/**
 * Users (6.4.2): everyone, masked, with filters. The search takes an id, the start of a
 * child's username, or an exact email address: the admin API looks an email up by its
 * hash, so searching never reveals one. The search is kept out of the URL (and so out of
 * the browser's history); the filters are in it, so a filtered list can be shared.
 */
import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { FlagBadges, Pill } from "@/components/badges";
import { DataTable, LoadMore, type Column } from "@/components/DataTable";
import { FilterBar, SearchBox, SelectFilter } from "@/components/Filters";
import { Identity } from "@/components/Identity";
import { PageHeader } from "@/components/Page";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { RelativeTime } from "@/components/Time";
import { api } from "@/lib/api";
import { formatCompact, formatInt, formatMoney, humanize } from "@/lib/format";
import { useOrgOptions, usePlans } from "@/lib/queries";
import type { Page, UserRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const FILTERS = ["kind", "role", "plan", "org", "active", "status", "sort"] as const;

export default function Users() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const plans = usePlans();
  const orgs = useOrgOptions();
  const filters = Object.fromEntries(FILTERS.map((k) => [k, params.get(k)])) as Record<(typeof FILTERS)[number], string | null>;

  const set = (key: (typeof FILTERS)[number], value: string | null) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );

  const users = useInfiniteQuery({
    queryKey: ["users", filters, q],
    queryFn: ({ pageParam }) => api.get<Page<UserRow>>("/users", { ...filters, q, cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
  });
  const rows = users.data?.pages.flatMap((p) => p.items) ?? [];

  const columns: Column<UserRow>[] = [
    { key: "id", header: "ID", numeric: true, cell: (u) => <span className="text-muted-foreground">{u.id}</span> },
    { key: "who", header: "Person", cell: (u) => <Identity id={u.id} identity={u.identity} kind={u.kind} link={false} className="max-w-[16rem]" /> },
    { key: "role", header: "Role", cell: (u) => <span className="text-muted-foreground">{u.role ? humanize(u.role) : "Not chosen"}</span> },
    {
      key: "plan",
      header: "Plan",
      cell: (u) =>
        u.plan ? (
          <span title={`From ${u.plan.source === "user" ? "their own assignment" : u.plan.source === "organization" ? "their organisation" : "the default"}`}>
            {u.plan.name}
            {u.plan.status === "trial" ? <Pill className="ml-1">Trial</Pill> : null}
          </span>
        ) : (
          "—"
        ),
    },
    { key: "org", header: "Organisation", cell: (u) => <span className="block max-w-[10rem] truncate">{u.organization?.name ?? "—"}</span> },
    { key: "created", header: "Joined", cell: (u) => <RelativeTime iso={u.created_at} /> },
    { key: "login", header: "Last sign-in", cell: (u) => <RelativeTime iso={u.last_login} /> },
    { key: "seen", header: "Last seen", cell: (u) => <RelativeTime iso={u.last_seen_at} /> },
    { key: "sessions", header: "Sessions", numeric: true, cell: (u) => formatInt(u.live_sessions) },
    { key: "tokens", header: "Tokens 30d", numeric: true, cell: (u) => (u.usage_30d.tokens ? formatCompact(u.usage_30d.tokens) : "—") },
    { key: "cost", header: "Cost 30d", numeric: true, cell: (u) => formatMoney(u.usage_30d.cost_usd) },
    { key: "tickets", header: "Open tickets", numeric: true, cell: (u) => (u.open_tickets ? formatInt(u.open_tickets) : "—") },
    { key: "flags", header: "Flags", cell: (u) => <FlagBadges flags={u.flags} hide={u.kind === "managed_child" ? ["child"] : []} /> },
  ];

  return (
    <div>
      <PageHeader title="Users" description="Everyone with an account. Emails and usernames are masked; exact-email search works without revealing." />
      <FilterBar>
        <SearchBox value={q} onSearch={setQ} placeholder="ID, exact email, or username" label="Search users" />
        <SelectFilter label="Kind" value={filters.kind} onChange={(v) => set("kind", v)} options={[{ value: "standard", label: "Standard" }, { value: "managed_child", label: "Child profiles" }]} />
        <SelectFilter
          label="Role"
          value={filters.role}
          onChange={(v) => set("role", v)}
          options={[
            { value: "student", label: "Student" },
            { value: "teacher", label: "Teacher" },
            { value: "none", label: "Not chosen" },
          ]}
        />
        <SelectFilter label="Plan" value={filters.plan} onChange={(v) => set("plan", v)} options={(plans.data?.items ?? []).map((p) => ({ value: p.id, label: p.name }))} />
        <SelectFilter
          label="Organisation"
          value={filters.org}
          onChange={(v) => set("org", v)}
          options={(orgs.data?.items ?? []).map((o) => ({ value: String(o.id), label: o.name }))}
        />
        <SelectFilter
          label="Active"
          allLabel="Any time"
          value={filters.active}
          onChange={(v) => set("active", v)}
          options={[
            { value: "today", label: "Today" },
            { value: "7d", label: "Last 7 days" },
            { value: "30d", label: "Last 30 days" },
            { value: "never", label: "Never" },
          ]}
        />
        <SelectFilter
          label="Status"
          value={filters.status}
          onChange={(v) => set("status", v)}
          options={[
            { value: "active", label: "Active" },
            { value: "deactivated", label: "Deactivated" },
            { value: "deleted", label: "Deleted" },
          ]}
        />
        <SelectFilter
          label="Sort"
          allLabel="Newest first"
          value={filters.sort}
          onChange={(v) => set("sort", v)}
          options={[
            { value: "oldest", label: "Oldest first" },
            { value: "last_seen", label: "Last seen" },
            { value: "last_sign_in", label: "Last sign-in" },
            { value: "cost_30d", label: "Cost, 30 days" },
            { value: "tokens_30d", label: "Tokens, 30 days" },
          ]}
        />
      </FilterBar>
      <div className="rounded-lg border bg-card">
        {users.isPending ? (
          <LoadingBlock rows={10} className="p-3" />
        ) : users.isError && !users.data ? (
          <ErrorState error={users.error} onRetry={() => void users.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title="No one matches">
            {q ? "An email search matches only the whole address. Try the ID, or the first letters of a child's username." : "Try fewer filters."}
          </EmptyState>
        ) : (
          <div className={cn("transition-opacity", users.isFetching && users.isPlaceholderData && "opacity-60")}>
            <DataTable label="Users" rows={rows} columns={columns} rowKey={(u) => u.id} onRowClick={(u) => navigate(`/users/${u.id}`)} />
            <LoadMore hasMore={!!users.hasNextPage} loading={users.isFetchingNextPage} onClick={() => void users.fetchNextPage()} shown={rows.length} />
          </div>
        )}
      </div>
    </div>
  );
}
