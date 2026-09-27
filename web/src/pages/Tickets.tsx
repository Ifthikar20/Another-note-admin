/**
 * Tickets (6.4.4): the inbox. Queues by status, filters, a live unread marker, and the
 * keyboard: J and K move, Enter opens, R opens and starts a reply.
 */
import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { PriorityBadge, TicketStatusBadge } from "@/components/badges";
import { DataTable, LoadMore, type Column } from "@/components/DataTable";
import { FilterBar, SearchBox, SelectFilter } from "@/components/Filters";
import { Identity } from "@/components/Identity";
import { PageHeader } from "@/components/Page";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { RelativeTime } from "@/components/Time";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatInt } from "@/lib/format";
import { useLiveTickets } from "@/lib/live";
import { REASONS } from "@/lib/series";
import type { TicketList, TicketRow, TicketStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export const QUEUES: { value: TicketStatus | "all"; label: string }[] = [
  { value: "open", label: "New" },
  { value: "waiting_on_us", label: "Waiting on us" },
  { value: "waiting_on_user", label: "Waiting on user" },
  { value: "resolved", label: "Resolved" },
  { value: "all", label: "All" },
];

/** The order of the list last shown, so J and K work on a ticket's own page too. */
export const QUEUE_ORDER_KEY = "admin.tickets.order";

export default function Tickets() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { unread, enabled: live, connected, markAllRead } = useLiveTickets();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState(0);
  const queue = (params.get("queue") as TicketStatus | "all" | null) ?? "open";
  const reason = params.get("reason");
  const priority = params.get("priority");
  const assignee = params.get("assignee");

  const set = (key: string, value: string | null) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );

  const tickets = useInfiniteQuery({
    queryKey: ["tickets", { queue, reason, priority, assignee, q }],
    queryFn: ({ pageParam }) =>
      api.get<TicketList>("/tickets", { status: queue === "all" ? null : queue, reason, priority, assignee, q, cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
    refetchInterval: live ? false : 60_000,
  });
  const rows = useMemo(() => tickets.data?.pages.flatMap((p) => p.items) ?? [], [tickets.data]);
  const counts = tickets.data?.pages[0]?.counts;

  useEffect(() => {
    setSelected(0);
  }, [queue, reason, priority, assignee, q]);

  useEffect(() => {
    try {
      sessionStorage.setItem(QUEUE_ORDER_KEY, JSON.stringify(rows.map((r) => r.number)));
    } catch {
      /* ignore */
    }
  }, [rows]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.closest("[role=dialog],[role=listbox],[role=menu]"))) return;
      if (e.key === "j") {
        setSelected((i) => Math.min(rows.length - 1, i + 1));
        e.preventDefault();
      } else if (e.key === "k") {
        setSelected((i) => Math.max(0, i - 1));
        e.preventDefault();
      } else if ((e.key === "Enter" || e.key === "o") && rows[selected]) {
        navigate(`/tickets/${rows[selected].number}`);
        e.preventDefault();
      } else if (e.key === "r" && rows[selected]) {
        navigate(`/tickets/${rows[selected].number}?reply=1`);
        e.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, selected, navigate]);

  const columns: Column<TicketRow>[] = [
    {
      key: "n",
      header: "Ticket",
      cell: (t) => (
        <span className="inline-flex items-center gap-2 whitespace-nowrap">
          <span
            className={cn("size-2 rounded-full", unread.has(t.id) ? "bg-strip" : "bg-transparent")}
            aria-label={unread.has(t.id) ? "Unread" : undefined}
          />
          <span className={cn(unread.has(t.id) && "font-semibold")}>{t.number}</span>
        </span>
      ),
    },
    {
      key: "s",
      header: "Subject",
      cell: (t) => (
        <span className="block max-w-xl">
          <span className={cn("line-clamp-1", unread.has(t.id) ? "font-semibold" : "font-medium")}>{t.subject || t.reason_label}</span>
          <span className="line-clamp-1 text-[12px] text-muted-foreground">{t.preview}</span>
        </span>
      ),
    },
    { key: "who", header: "From", cell: (t) => <Identity id={t.user.id} identity={t.user.identity} kind={t.user.kind} className="max-w-[13rem]" /> },
    { key: "reason", header: "About", cell: (t) => <span className="block max-w-[11rem] truncate text-muted-foreground" title={t.reason_label}>{REASONS.find((r) => r.id === t.reason)?.label ?? t.reason_label}</span> },
    { key: "p", header: "Priority", cell: (t) => <PriorityBadge priority={t.priority} /> },
    ...(queue === "all" ? [{ key: "st", header: "Status", cell: (t: TicketRow) => <TicketStatusBadge status={t.status} /> }] : []),
    { key: "a", header: "Assignee", cell: (t) => <span className="block max-w-[10rem] truncate text-muted-foreground">{t.assignee_email ?? "Nobody"}</span> },
    { key: "u", header: queue === "open" || queue === "waiting_on_us" ? "Waiting since" : "Updated", cell: (t) => <RelativeTime iso={queue === "open" || queue === "waiting_on_us" ? t.last_user_at ?? t.created_at : t.updated_at} /> },
  ];

  return (
    <div>
      <PageHeader
        title="Tickets"
        description={
          <>
            What people wrote to support, and the conversation. Keys: <kbd className="rounded border px-1">J</kbd> <kbd className="rounded border px-1">K</kbd> move,{" "}
            <kbd className="rounded border px-1">Enter</kbd> opens, <kbd className="rounded border px-1">R</kbd> replies.
          </>
        }
        actions={
          live ? (
            <>
              <span className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
                <span className={cn("size-2 rounded-full", connected ? "bg-[hsl(var(--success))]" : "bg-muted-foreground")} />
                {connected ? "Live" : "Reconnecting"}
              </span>
              {unread.size ? (
                <Button variant="outline" size="sm" onClick={markAllRead}>
                  Mark {formatInt(unread.size)} read
                </Button>
              ) : null}
            </>
          ) : null
        }
      />
      <div className="mb-3 flex flex-wrap gap-1 border-b" role="tablist" aria-label="Queues">
        {QUEUES.map((qu) => {
          const count = qu.value === "all" || !counts ? null : counts[qu.value];
          return (
            <button
              key={qu.value}
              type="button"
              role="tab"
              aria-selected={queue === qu.value}
              onClick={() => set("queue", qu.value === "open" ? null : qu.value)}
              className={cn(
                "-mb-px border-b-2 px-3 py-2 text-[13px]",
                queue === qu.value ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {qu.label}
              {count !== null ? <span className="num ml-1.5 text-muted-foreground">{formatInt(count)}</span> : null}
            </button>
          );
        })}
      </div>
      <FilterBar>
        <SearchBox value={q} onSearch={setQ} placeholder="AN-0042 or words in the subject" label="Search tickets" />
        <SelectFilter label="About" value={reason} onChange={(v) => set("reason", v)} options={REASONS.map((r) => ({ value: r.id, label: r.label }))} />
        <SelectFilter
          label="Priority"
          value={priority}
          onChange={(v) => set("priority", v)}
          options={[
            { value: "urgent", label: "Urgent" },
            { value: "high", label: "High" },
            { value: "normal", label: "Normal" },
            { value: "low", label: "Low" },
          ]}
        />
        <SelectFilter
          label="Assignee"
          allLabel="Anyone"
          value={assignee}
          onChange={(v) => set("assignee", v)}
          options={[
            { value: "me", label: "Me" },
            { value: "none", label: "Nobody" },
          ]}
        />
      </FilterBar>
      <div className="rounded-lg border bg-card">
        {tickets.isPending ? (
          <LoadingBlock rows={8} className="p-3" />
        ) : tickets.isError && !tickets.data ? (
          <ErrorState error={tickets.error} onRetry={() => void tickets.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title={queue === "open" ? "No new tickets" : "Nothing in this queue"}>{q || reason || priority || assignee ? "Try fewer filters." : null}</EmptyState>
        ) : (
          <div className={cn("transition-opacity", tickets.isFetching && tickets.isPlaceholderData && "opacity-60")}>
            <DataTable
              label="Tickets"
              rows={rows}
              columns={columns}
              rowKey={(t) => t.id}
              selectedIndex={selected}
              onRowClick={(t) => navigate(`/tickets/${t.number}`)}
            />
            <LoadMore hasMore={!!tickets.hasNextPage} loading={tickets.isFetchingNextPage} onClick={() => void tickets.fetchNextPage()} shown={rows.length} />
          </div>
        )}
      </div>
    </div>
  );
}
