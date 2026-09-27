/**
 * Settings (6.4.10, owner): the admin members and what each role allows, the access
 * review (evidence for a periodic review of who has access), the session rules, the price
 * table in force, and whether the admin API is healthy.
 */
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Pill, RoleBadge } from "@/components/badges";
import { DataTable } from "@/components/DataTable";
import { Facts, PageHeader, Section } from "@/components/Page";
import { EmptyState, QueryView } from "@/components/states";
import { RelativeTime } from "@/components/Time";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, download, errorMessage } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/me";
import type { AccessReview, Health, Prices } from "@/lib/types";

const ROLE_TEXT: Record<string, string> = {
  owner: "Everything, including deactivating accounts, plans, the audit log and these settings.",
  support: "Tickets, revealing an email with a reason, signing someone out everywhere, and security events.",
  analyst: "Overview, users (masked), usage and cost, and activity totals. No tickets or security events.",
  viewer: "Overview, users (masked), usage, and reading tickets. No actions.",
};

export default function SettingsPage() {
  const me = useMe();
  const review = useQuery({ queryKey: ["settings", "access-review"], queryFn: () => api.get<AccessReview>("/settings/access-review") });
  const prices = useQuery({ queryKey: ["settings", "prices"], queryFn: () => api.get<Prices>("/settings/prices"), retry: false });
  const health = useQuery({ queryKey: ["health"], queryFn: () => api.get<Health>("/health") });
  const [exporting, setExporting] = useState(false);

  return (
    <div className="space-y-4">
      <PageHeader title="Settings" description="Who can use this app and with what role, the session rules, and the prices in force." />

      <Section
        title="Access review"
        description="Every admin member, their role, and their last recorded admin action. Review it every quarter, and when someone changes jobs or leaves."
        actions={
          <Button
            variant="outline"
            size="sm"
            disabled={exporting}
            onClick={async () => {
              setExporting(true);
              try {
                await download("/settings/access-review.csv", "access-review.csv");
                toast("Access review downloaded: record a decision for each row and file it");
              } catch (e) {
                toast.error(errorMessage(e));
              } finally {
                setExporting(false);
              }
            }}
          >
            <Download /> {exporting ? "Preparing…" : "Download for review (CSV)"}
          </Button>
        }
        bodyClassName="p-0"
      >
        <QueryView query={review} isEmpty={(r) => !r.items.length} empty={<EmptyState title="No members listed">ADMIN_MEMBERS is empty.</EmptyState>}>
          {(r) => (
            <>
              <DataTable
                label="Admin members"
                rows={r.items}
                rowKey={(m) => m.email}
                columns={[
                  {
                    key: "email",
                    header: "Member",
                    cell: (m) => (
                      <span>
                        {m.email}
                        {m.dev_identity ? <Pill className="ml-1.5">Development identity</Pill> : null}
                      </span>
                    ),
                  },
                  {
                    key: "role",
                    header: "Role",
                    cell: (m) => (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span>
                            <RoleBadge role={m.role} />
                          </span>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs">{ROLE_TEXT[m.role]}</TooltipContent>
                      </Tooltip>
                    ),
                  },
                  { key: "caps", header: "Can", cell: (m) => <span className="line-clamp-2 max-w-md text-[12px] text-muted-foreground">{m.capabilities.join(", ")}</span> },
                  {
                    key: "last",
                    header: "Last admin action",
                    cell: (m) =>
                      m.last_admin_action_at ? (
                        <span>
                          <RelativeTime iso={m.last_admin_action_at} /> <span className="text-muted-foreground">({m.last_admin_action})</span>
                        </span>
                      ) : (
                        <span className="text-muted-foreground">None recorded</span>
                      ),
                  },
                ]}
              />
              <div className="space-y-1 border-t px-4 py-3 text-[12px] text-muted-foreground">
                <p>Access is granted in two places, and both must agree: {r.sources.join("; and ")}.</p>
                <p>Members are read from this app's configuration. To add, change or remove one, update both, and redeploy (see docs/DEPLOY.md, "Add or remove an admin").</p>
              </div>
            </>
          )}
        </QueryView>
      </Section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Sessions">
          <Facts
            items={[
              ["Signed in as", <span key="me">{me.email} <RoleBadge role={me.role} /></span>],
              ["Sign-in", me.dev_identity ? "Development identity (this machine only)" : "Cloudflare Access: single sign-on with multi-factor"],
              ["Screen lock", `After ${me.idle_lock_minutes} minutes without activity; cached data is cleared`],
              ["Sign-out", me.sign_out_url ? `After ${me.idle_sign_out_minutes} minutes without activity, and at the end of the Access session` : "Not applicable in development"],
              ["Revealed emails", "Shown for 60 seconds, then masked again; every reveal is audited"],
            ]}
          />
        </Section>
        <Section title="Health">
          <QueryView query={health}>
            {(h) => (
              <Facts
                items={[
                  ["Admin API", h.admin_api.ok ? <Pill key="ok" variant="good">Up</Pill> : <Pill key="down" variant="bad">{h.admin_api.error ?? "Down"}</Pill>],
                  ["Database", h.admin_api.db === undefined ? "—" : h.admin_api.db ? "Up" : "Down"],
                  ["Cache", h.admin_api.redis === undefined ? "—" : h.admin_api.redis ? "Up" : "Down"],
                  ["Admin API version", h.admin_api.version ?? "—"],
                  ["This app's version", h.bff_version],
                  ["Environment", me.environment],
                ]}
              />
            )}
          </QueryView>
        </Section>
      </div>

      <Section title="Prices in force" description="Set in the backend (app/core/usage_prices.py, or the USAGE_PRICES_JSON override). A change applies to new calls only." bodyClassName="p-0">
        <QueryView query={prices} isEmpty={(p) => !p.items.length} empty={<EmptyState title="No prices set" />}>
          {(p) => (
            <>
              <DataTable
                label="Prices"
                rows={p.items}
                rowKey={(r) => `${r.provider}/${r.model}`}
                columns={[
                  { key: "p", header: "Provider", cell: (r) => r.provider },
                  { key: "m", header: "Model", cell: (r) => <code className="text-[12px]">{r.model}</code> },
                  { key: "in", header: "Input / 1M tokens", numeric: true, cell: (r) => formatMoney(r.input_per_mtok) },
                  { key: "out", header: "Output / 1M", numeric: true, cell: (r) => formatMoney(r.output_per_mtok) },
                  { key: "cr", header: "Cache read / 1M", numeric: true, cell: (r) => formatMoney(r.cache_read_per_mtok) },
                  { key: "cw", header: "Cache write / 1M", numeric: true, cell: (r) => formatMoney(r.cache_write_per_mtok) },
                  { key: "ch", header: "/ 1M characters", numeric: true, cell: (r) => formatMoney(r.per_mchar) },
                  { key: "rq", header: "/ request", numeric: true, cell: (r) => formatMoney(r.per_request) },
                ]}
              />
              <p className="border-t px-4 py-2 text-[12px] text-muted-foreground">
                Source: {p.source}. Monthly AI budget: {p.budget_month_usd !== null ? formatMoney(p.budget_month_usd) : "not set"}. A dash means no price yet: those calls count in units, not cost.
              </p>
            </>
          )}
        </QueryView>
      </Section>
    </div>
  );
}
