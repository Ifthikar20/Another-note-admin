/**
 * Audit log (6.4.9, owner): every request any admin made, with who, what, which record and
 * why. Append-only: the admin API's database role can add rows and read them, never change
 * or delete them. The export is of this log only (no personal data beyond staff emails).
 */
import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Pill, RoleBadge } from "@/components/badges";
import { DataTable, LoadMore } from "@/components/DataTable";
import { FilterBar, SearchBox, SelectFilter } from "@/components/Filters";
import { PageHeader } from "@/components/Page";
import { RangePicker } from "@/components/RangePicker";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { ExactTime } from "@/components/Time";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { api, download, errorMessage } from "@/lib/api";
import { formatInt, humanize, ticketNumber } from "@/lib/format";
import { rangeLabel, useRange } from "@/lib/range";
import type { AuditRow, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

const ACTIONS = [
  "view.overview",
  "view.users",
  "view.user",
  "view.usage",
  "view.activity",
  "view.tickets",
  "view.security",
  "view.plans",
  "view.orgs",
  "view.events",
  "user.reveal_email",
  "user.sign_out_everywhere",
  "user.deactivate",
  "user.reactivate",
  "plan.assign",
  "plan.create",
  "plan.update",
  "ticket.view",
  "ticket.reply",
  "ticket.note",
  "ticket.update",
  "picture.block",
  "picture.unblock",
  "audit.view",
];

function Target({ row }: { row: AuditRow }) {
  if (!row.target_type || !row.target_id) return <span className="text-muted-foreground">—</span>;
  if (row.target_type === "user") return <Link to={`/users/${row.target_id}`} className="hover:underline">User #{row.target_id}</Link>;
  if (row.target_type === "ticket") return <Link to={`/tickets/${ticketNumber(Number(row.target_id))}`} className="hover:underline">{ticketNumber(Number(row.target_id))}</Link>;
  if (row.target_type === "organization") return <Link to={`/orgs?org=${row.target_id}`} className="hover:underline">Organisation {row.target_id}</Link>;
  if (row.target_type === "plan") return <Link to="/plans" className="hover:underline">Plan {row.target_id}</Link>;
  return <span>{humanize(row.target_type)} {row.target_id}</span>;
}

export default function Audit() {
  const [range] = useRange("30d");
  const [params, setParams] = useSearchParams();
  const action = params.get("action");
  const actor = params.get("actor") ?? "";
  // The live ticket stream's own requests (view.events) are audited like any other, and
  // would bury everything else: they are left out unless asked for.
  const background = params.get("background") === "1";
  const [exporting, setExporting] = useState(false);
  const filters = { actor: actor || null, action, exclude: background || action ? null : "view.events", from: range.from, to: range.to };
  const audit = useInfiniteQuery({
    queryKey: ["audit", filters],
    queryFn: ({ pageParam }) => api.get<Page<AuditRow>>("/audit", { ...filters, cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
  });
  const rows = audit.data?.pages.flatMap((p) => p.items) ?? [];
  const set = (key: string, value: string | null) =>
    setParams((p) => { const n = new URLSearchParams(p); if (value) n.set(key, value); else n.delete(key); return n; }, { replace: true });

  return (
    <div>
      <PageHeader
        title="Audit log"
        description={`Every admin request: who, what, which record and why · ${rangeLabel(range)}. Kept for a year; rows can't be changed or deleted.`}
        actions={
          <>
            <RangePicker />
            <Button
              variant="outline"
              size="sm"
              disabled={exporting}
              onClick={async () => {
                setExporting(true);
                try {
                  const q = new URLSearchParams(Object.entries(filters).filter(([, v]) => v) as [string, string][]);
                  const r = await download(`/audit/export.csv?${q.toString()}`, "audit.csv");
                  toast(r.truncated ? `Exported the first ${formatInt(r.rows)} rows: narrow the range for the rest` : `Exported ${formatInt(r.rows)} rows`);
                } catch (e) {
                  toast.error(errorMessage(e));
                } finally {
                  setExporting(false);
                }
              }}
            >
              <Download /> {exporting ? "Exporting…" : "Export CSV"}
            </Button>
          </>
        }
      />
      <FilterBar>
        <SearchBox value={actor} onSearch={(v) => set("actor", v || null)} placeholder="Staff email" label="Actor" />
        <SelectFilter label="Action" value={action} onChange={(v) => set("action", v)} options={ACTIONS.map((a) => ({ value: a, label: a }))} />
        <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <Checkbox checked={background} onCheckedChange={(v) => set("background", v === true ? "1" : null)} disabled={!!action} />
          Include live-update requests (view.events)
        </label>
      </FilterBar>
      <div className="rounded-lg border bg-card">
        {audit.isPending ? (
          <LoadingBlock rows={10} className="p-3" />
        ) : audit.isError && !audit.data ? (
          <ErrorState error={audit.error} onRetry={() => void audit.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title="No admin actions match" />
        ) : (
          <div className={cn("transition-opacity", audit.isFetching && audit.isPlaceholderData && "opacity-60")}>
            <DataTable
              label="Audit log"
              rows={rows}
              rowKey={(r) => r.id}
              columns={[
                { key: "at", header: "When", cell: (r) => <ExactTime iso={r.at} /> },
                { key: "actor", header: "Who", cell: (r) => <span className="inline-flex items-center gap-1.5"><span className="max-w-[14rem] truncate">{r.actor_email}</span> <RoleBadge role={r.actor_role} /></span> },
                {
                  key: "action",
                  header: "Action",
                  cell: (r) => (
                    <Pill variant={r.action.startsWith("view.") || r.action === "audit.view" || r.action === "ticket.view" ? "neutral" : "accent"}>{r.action}</Pill>
                  ),
                },
                { key: "target", header: "Record", cell: (r) => <Target row={r} /> },
                { key: "reason", header: "Reason", cell: (r) => <span className="line-clamp-2 max-w-sm">{r.reason ?? "—"}</span> },
                {
                  key: "details",
                  header: "Details",
                  cell: (r) =>
                    r.details ? (
                      <code className="block max-w-[14rem] truncate text-[11px] text-muted-foreground" title={JSON.stringify(r.details)}>
                        {Object.entries(r.details).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join("|") : String(v)}`).join(" ")}
                      </code>
                    ) : (
                      "—"
                    ),
                },
                { key: "rid", header: "Request", cell: (r) => <code className="text-[11px] text-muted-foreground" title={r.request_id ?? undefined}>{r.request_id?.slice(0, 8) ?? "—"}</code> },
              ]}
            />
            <LoadMore hasMore={!!audit.hasNextPage} loading={audit.isFetchingNextPage} onClick={() => void audit.fetchNextPage()} shown={rows.length} />
          </div>
        )}
      </div>
    </div>
  );
}
