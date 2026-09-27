/**
 * Organisations (6.4.7): schools and districts, their members, single sign-on, and plan.
 */
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Pill } from "@/components/badges";
import { DataTable, LoadMore } from "@/components/DataTable";
import { FilterBar, SearchBox } from "@/components/Filters";
import { Facts, PageHeader, Section } from "@/components/Page";
import { PlanChangeDialog } from "@/components/PlanChangeDialog";
import { EmptyState, ErrorState, LoadingBlock, QueryView } from "@/components/states";
import { ExactTime, RelativeTime } from "@/components/Time";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api } from "@/lib/api";
import { formatInt, providerLabel } from "@/lib/format";
import { useCan } from "@/lib/me";
import type { OrgDetail, OrgRow, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

import { PlanHistory } from "./UserDetail";

export default function Orgs() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const open = params.get("org");
  const orgs = useInfiniteQuery({
    queryKey: ["orgs", "list", q],
    queryFn: ({ pageParam }) => api.get<Page<OrgRow>>("/orgs", { q, cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
  });
  const rows = orgs.data?.pages.flatMap((p) => p.items) ?? [];
  const setOpen = (id: number | null) =>
    setParams((p) => { const n = new URLSearchParams(p); if (id) n.set("org", String(id)); else n.delete("org"); return n; }, { replace: true });

  return (
    <div>
      <PageHeader title="Organisations" description="Schools and districts: how many members, how they sign in, and their plan." />
      <FilterBar>
        <SearchBox value={q} onSearch={setQ} placeholder="Name, slug or domain" label="Search organisations" />
      </FilterBar>
      <div className="rounded-lg border bg-card">
        {orgs.isPending ? (
          <LoadingBlock className="p-3" />
        ) : orgs.isError && !orgs.data ? (
          <ErrorState error={orgs.error} onRetry={() => void orgs.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title="No organisations match" />
        ) : (
          <div className={cn("transition-opacity", orgs.isFetching && orgs.isPlaceholderData && "opacity-60")}>
            <DataTable
              label="Organisations"
              rows={rows}
              rowKey={(o) => o.id}
              onRowClick={(o) => setOpen(o.id)}
              columns={[
                { key: "name", header: "Name", cell: (o) => <span className="font-medium">{o.name}</span> },
                { key: "slug", header: "Slug", cell: (o) => <code className="text-[12px] text-muted-foreground">{o.slug}</code> },
                { key: "sso", header: "Single sign-on", cell: (o) => (o.sso_provider ? <span>{providerLabel(o.sso_provider)}{o.sso_enforced ? <Pill className="ml-1.5">Required</Pill> : null}</span> : "Any provider") },
                { key: "members", header: "Members", numeric: true, cell: (o) => formatInt(o.members) },
                { key: "plan", header: "Plan", cell: (o) => o.plan?.name ?? "—" },
                { key: "created", header: "Since", cell: (o) => <RelativeTime iso={o.created_at} /> },
              ]}
            />
            <LoadMore hasMore={!!orgs.hasNextPage} loading={orgs.isFetchingNextPage} onClick={() => void orgs.fetchNextPage()} shown={rows.length} />
          </div>
        )}
      </div>
      <Sheet open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">{open ? <OrgPanel id={Number(open)} /> : null}</SheetContent>
      </Sheet>
    </div>
  );
}

function OrgPanel({ id }: { id: number }) {
  const canPlan = useCan("plans.write");
  const org = useQuery({ queryKey: ["org", id], queryFn: () => api.get<OrgDetail>(`/orgs/${id}`) });
  return (
    <QueryView query={org} loading={<LoadingBlock rows={6} />}>
      {(d) => (
        <div className="space-y-4">
          <SheetHeader>
            <SheetTitle>{d.org.name}</SheetTitle>
            <SheetDescription>
              <code>{d.org.slug}</code> · since <ExactTime iso={d.org.created_at} />
            </SheetDescription>
          </SheetHeader>
          <Section title="Members">
            <Facts
              items={[
                ["Members", <Link key="m" to={`/users?org=${d.org.id}`} className="underline">{formatInt(d.member_counts.total)}</Link>],
                ["Teachers", formatInt(d.member_counts.teachers)],
                ["Students", formatInt(d.member_counts.students)],
                ["Organisation owners", formatInt(d.member_counts.org_owners)],
                ["Organisation admins", formatInt(d.member_counts.org_admins)],
              ]}
            />
          </Section>
          <Section title="Single sign-on and domains">
            <Facts
              items={[
                ["Provider", d.org.sso_provider ? providerLabel(d.org.sso_provider) : "Any configured provider"],
                ["Required", d.org.sso_enforced ? "Yes: members must use it" : "No"],
                [
                  "Domains",
                  <ul key="d" className="space-y-0.5">
                    {d.domains.map((dom) => (
                      <li key={dom.domain}>
                        {dom.domain} {dom.verified ? <Pill variant="good">Verified</Pill> : <Pill>Not verified</Pill>}
                      </li>
                    ))}
                  </ul>,
                ],
              ]}
            />
          </Section>
          <Section title="Plan" actions={canPlan ? <PlanChangeDialog subject="org" id={d.org.id} currentPlanId={d.plan.effective.plan.id} hasOwnAssignment={d.plan.effective.source === "organization"} /> : null}>
            <PlanHistory plan={d.plan} />
          </Section>
        </div>
      )}
    </QueryView>
  );
}
