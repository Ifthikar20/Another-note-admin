/**
 * A person (6.4.3): who they are (masked), what they use, and the audited actions. Counts
 * and sizes only: nothing they wrote or studied is ever shown here.
 */
import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, LogOut, Power, PowerOff } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { AuditBadge } from "@/components/AuditBadge";
import { FlagBadges, Pill, TicketStatusBadge, UserStatusBadge } from "@/components/badges";
import { ChartCard, RankedBars, SingleBars } from "@/components/charts";
import { DataTable, LoadMore } from "@/components/DataTable";
import { UserLink } from "@/components/Identity";
import { Facts, PageHeader, Section } from "@/components/Page";
import { PlanChangeDialog } from "@/components/PlanChangeDialog";
import { RangePicker } from "@/components/RangePicker";
import { ReasonDialog } from "@/components/ReasonDialog";
import { RevealEmail } from "@/components/RevealEmail";
import { StatGrid, StatTile } from "@/components/Stat";
import { EmptyState, ErrorState, LoadingBlock, QueryView } from "@/components/states";
import { ExactTime, RelativeTime } from "@/components/Time";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import {
  ageBandLabel,
  formatAudioMinutes,
  formatBytes,
  formatCompact,
  formatDuration,
  formatInt,
  formatMoney,
  humanize,
  providerLabel,
} from "@/lib/format";
import { useCan } from "@/lib/me";
import { ACCENT, featureLabel } from "@/lib/series";
import { daysBetween, rangeLabel, useRange } from "@/lib/range";
import type {
  AnalyticsEvent,
  AuthEvent,
  LiveSession,
  Page,
  SubjectPlan,
  TicketList,
  UsageGroup,
  UsageSummary,
  UserDetail as UserDetailT,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export default function UserDetail() {
  const { id } = useParams();
  const userId = Number(id);
  const valid = Number.isInteger(userId) && userId > 0;
  const detail = useQuery({
    queryKey: ["user", userId],
    queryFn: () => api.get<UserDetailT>(`/users/${userId}`),
    enabled: valid,
  });
  if (!valid) return <EmptyState title="That isn't a user id" />;
  return (
    <div>
      <Link to="/users" className="mb-2 inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Users
      </Link>
      <QueryView query={detail} loading={<LoadingBlock rows={8} />}>
        {(d) => <Person d={d} />}
      </QueryView>
    </div>
  );
}

function Person({ d }: { d: UserDetailT }) {
  const u = d.user;
  const [params, setParams] = useSearchParams();
  const canTickets = useCan("users.tickets");
  const canSecurity = useCan("users.auth_events");
  const canActivity = useCan("activity.read");
  const canSignOut = useCan("users.sign_out");
  const canSetActive = useCan("users.set_active");
  const canPlan = useCan("plans.write");
  const tab = params.get("tab") ?? "activity";
  const title = u.identity.email_masked ?? u.identity.username_masked ?? `#${u.id}`;

  return (
    <>
      <PageHeader
        title={`${u.identity.first_name || "Unnamed"} · #${u.id}`}
        description={
          <span className="inline-flex flex-wrap items-center gap-1.5">
            <Pill>{u.kind === "managed_child" ? "Child profile" : "Standard account"}</Pill>
            {u.role ? <Pill>{humanize(u.role)}</Pill> : null}
            <Pill title="From the birth year; the year itself is never shown">{ageBandLabel(u.age_band)}</Pill>
            <UserStatusBadge status={u.status} />
            <FlagBadges flags={u.flags} hide={["deactivated", "deleted", "child"]} />
          </span>
        }
      />
      <div className="mb-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Section title="Identity" description="Masked. Revealing the email is audited.">
          <Facts
            items={[
              [u.identity.email_masked ? "Email" : "Username", u.identity.email_masked ? <RevealEmail userId={u.id} masked={u.identity.email_masked} /> : <span className="font-medium">{title}</span>],
              ["First name", u.identity.first_name || "—"],
              ["Signs in with", d.profile.auth_provider ? providerLabel(d.profile.auth_provider) : u.kind === "managed_child" ? "Child PIN" : "—"],
              ["Organisation", u.organization ? `${u.organization.name}${d.profile.org_role ? ` (${d.profile.org_role})` : ""}` : "—"],
              ["Joined", <ExactTime key="j" iso={u.created_at} />],
              ["Onboarding", d.profile.onboarding_completed ? "Done" : "Not finished"],
              ["XP", formatInt(d.profile.xp)],
            ]}
          />
        </Section>
        <Section
          title="Plan"
          description={u.plan ? `From ${u.plan.source === "user" ? "their own assignment" : u.plan.source === "organization" ? "their organisation" : "the default plan"}` : undefined}
          actions={canPlan ? <PlanChangeDialog subject="user" id={u.id} currentPlanId={u.plan?.id} hasOwnAssignment={u.plan?.source === "user"} /> : null}
        >
          <p className="text-lg font-semibold">
            {u.plan?.name ?? "—"} {u.plan?.status === "trial" ? <Pill>Trial</Pill> : null}
          </p>
          <StatGrid className="mt-3 grid-cols-2 md:grid-cols-2 xl:grid-cols-2">
            <StatTile label="Last seen" value={<RelativeTime iso={u.last_seen_at} />} sub={<>Last sign-in <RelativeTime iso={u.last_login} /></>} />
            <StatTile label="Live sessions" value={formatInt(u.live_sessions)} sub="Signed-in browsers and devices" />
            <StatTile label="AI tokens, 30 days" value={formatCompact(u.usage_30d.tokens)} sub={`${formatMoney(u.usage_30d.cost_usd)} of AI cost`} />
            <StatTile label="Open tickets" value={formatInt(u.open_tickets)} />
          </StatGrid>
        </Section>
      </div>

      <Tabs value={tab} onValueChange={(v) => setParams((p) => { const n = new URLSearchParams(p); n.set("tab", v); return n; }, { replace: true })}>
        <TabsList className="h-auto flex-wrap justify-start">
          <TabsTrigger value="activity">Activity</TabsTrigger>
          <TabsTrigger value="usage">Usage</TabsTrigger>
          <TabsTrigger value="footprint">Footprint</TabsTrigger>
          <TabsTrigger value="plan">Plan history</TabsTrigger>
          {canTickets ? <TabsTrigger value="support">Support</TabsTrigger> : null}
          <TabsTrigger value="family">Family</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          {canActivity ? <TabsTrigger value="app">App activity</TabsTrigger> : null}
          {canSignOut || canSetActive ? <TabsTrigger value="actions">Actions</TabsTrigger> : null}
        </TabsList>
        <TabsContent value="activity" className="mt-4 space-y-4">
          <ActivityTab d={d} />
        </TabsContent>
        <TabsContent value="usage" className="mt-4">
          <UsageTab userId={u.id} />
        </TabsContent>
        <TabsContent value="footprint" className="mt-4">
          <FootprintTab d={d} />
        </TabsContent>
        <TabsContent value="plan" className="mt-4">
          <PlanTab userId={u.id} />
        </TabsContent>
        {canTickets ? (
          <TabsContent value="support" className="mt-4">
            <SupportTab userId={u.id} />
          </TabsContent>
        ) : null}
        <TabsContent value="family" className="mt-4">
          <FamilyTab d={d} />
        </TabsContent>
        <TabsContent value="security" className="mt-4">
          <SecurityTab d={d} canEvents={canSecurity} />
        </TabsContent>
        {canActivity ? (
          <TabsContent value="app" className="mt-4">
            <AppActivityTab userId={u.id} />
          </TabsContent>
        ) : null}
        {canSignOut || canSetActive ? (
          <TabsContent value="actions" className="mt-4">
            <ActionsTab d={d} canSignOut={canSignOut} canSetActive={canSetActive} />
          </TabsContent>
        ) : null}
      </Tabs>
    </>
  );
}

function ActivityTab({ d }: { d: UserDetailT }) {
  const rows = d.activity_30d.map((a) => ({ day: a.day, minutes: Math.round(a.active_seconds / 60) }));
  const total = d.activity_30d.reduce((acc, a) => acc + a.active_seconds, 0);
  const sessions = useQuery({ queryKey: ["user", d.user.id, "sessions"], queryFn: () => api.get<Page<LiveSession>>(`/users/${d.user.id}/sessions`) });
  return (
    <>
      <ChartCard
        title="Active minutes per day"
        description={`Measured interaction time, last 30 UTC days · ${formatDuration(total)} in all`}
        table={{ columns: ["Day (UTC)", "Active minutes"], rows: rows.map((r) => [r.day, formatInt(r.minutes)]) }}
      >
        <SingleBars data={rows} dataKey="minutes" label="Active minutes" color={ACCENT} height={180} />
      </ChartCard>
      <Section title="Live sessions" description="Signed-in browsers and devices. Signing out everywhere ends them all." bodyClassName="p-0">
        <QueryView query={sessions} isEmpty={(s) => !s.items.length} empty={<EmptyState title="No live sessions" />}>
          {(s) => (
            <DataTable
              label="Live sessions"
              rows={s.items}
              rowKey={(r) => r.session_id}
              columns={[
                { key: "device", header: "Device", cell: (r) => r.device?.ua_family ?? <span className="text-muted-foreground">Not recorded</span> },
                { key: "country", header: "Country", cell: (r) => r.device?.country ?? "—" },
                { key: "method", header: "Signed in with", cell: (r) => providerLabel(r.device?.method) },
                { key: "since", header: "Signed in", cell: (r) => <RelativeTime iso={r.created_at} /> },
                { key: "used", header: "Last used", cell: (r) => <RelativeTime iso={r.device?.last_refresh_at} /> },
                { key: "expires", header: "Expires", cell: (r) => <RelativeTime iso={r.expires_at} /> },
              ]}
            />
          )}
        </QueryView>
      </Section>
    </>
  );
}

const GROUPS: { value: UsageGroup; label: string }[] = [
  { value: "feature", label: "Feature" },
  { value: "provider", label: "Provider" },
  { value: "model", label: "Model" },
  { value: "day", label: "Day" },
];

function UsageTab({ userId }: { userId: number }) {
  const [range] = useRange("30d");
  const [group, setGroup] = useState<UsageGroup>("feature");
  const usage = useQuery({
    queryKey: ["user", userId, "usage", group, range.from, range.to],
    queryFn: () => api.get<UsageSummary>(`/users/${userId}/usage`, { from: range.from, to: range.to, group }),
    placeholderData: keepPreviousData,
  });
  const days = useMemo(() => daysBetween(range.from, range.to), [range.from, range.to]);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <RangePicker />
        <Segmented value={group} onChange={setGroup} options={GROUPS} label="Group by" />
      </div>
      <QueryView query={usage}>
        {(u) => (
          <>
            <StatGrid>
              <StatTile label="AI tokens" value={formatCompact(u.totals.input_tokens + u.totals.output_tokens)} sub={`${formatCompact(u.totals.input_tokens)} in · ${formatCompact(u.totals.output_tokens)} out`} />
              <StatTile label="AI cost" value={formatMoney(u.totals.cost_usd)} sub={u.totals.unpriced_calls ? `${formatInt(u.totals.unpriced_calls)} calls without a price` : `${formatInt(u.totals.calls)} calls`} />
              <StatTile label="Voice" value={`${formatCompact(u.totals.characters)} chars`} sub="Text read aloud (Speechify)" />
              <StatTile label="Transcription" value={formatAudioMinutes(u.totals.audio_ms)} sub="Audio run through Whisper" />
            </StatGrid>
            {group === "day" ? (
              <ChartCard
                title="Tokens per day"
                description={`${rangeLabel(range)} · UTC days`}
                table={{ columns: ["Day (UTC)", "Tokens", "Cost"], rows: u.rows.map((r) => [r.key, formatInt(r.input_tokens + r.output_tokens), formatMoney(r.cost_usd)]) }}
              >
                <SingleBars
                  data={days.map((day) => {
                    const r = u.rows.find((x) => x.key === day);
                    return { day, tokens: r ? r.input_tokens + r.output_tokens : 0 };
                  })}
                  dataKey="tokens"
                  label="Tokens"
                  color={ACCENT}
                  height={180}
                />
              </ChartCard>
            ) : (
              <UsageTable summary={u} group={group} />
            )}
          </>
        )}
      </QueryView>
    </div>
  );
}

export function UsageTable({ summary, group }: { summary: UsageSummary; group: UsageGroup }) {
  if (!summary.rows.length) return <EmptyState title="No usage in this range" />;
  const label = (key: string) => (group === "feature" ? featureLabel(key) : key);
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Section title={`By ${group}`} bodyClassName="p-0">
        <DataTable
          label={`Usage by ${group}`}
          rows={summary.rows}
          rowKey={(r) => r.key}
          columns={[
            { key: "k", header: humanize(group), cell: (r) => <span title={r.key}>{label(r.key)}</span> },
            { key: "calls", header: "Calls", numeric: true, cell: (r) => formatInt(r.calls) },
            { key: "in", header: "Input tokens", numeric: true, cell: (r) => (r.input_tokens ? formatInt(r.input_tokens) : "—") },
            { key: "out", header: "Output tokens", numeric: true, cell: (r) => (r.output_tokens ? formatInt(r.output_tokens) : "—") },
            { key: "cache", header: "Cache reads", numeric: true, cell: (r) => (r.cache_read_tokens ? formatInt(r.cache_read_tokens) : "—") },
            { key: "chars", header: "Characters", numeric: true, cell: (r) => (r.characters ? formatInt(r.characters) : "—") },
            { key: "audio", header: "Audio", numeric: true, cell: (r) => (r.audio_ms ? formatAudioMinutes(r.audio_ms) : "—") },
            { key: "cost", header: "Cost", numeric: true, cell: (r) => <span title={r.unpriced_calls ? `${r.unpriced_calls} calls without a price` : undefined}>{formatMoney(r.cost_usd)}{r.unpriced_calls ? "*" : ""}</span> },
          ]}
        />
        {summary.totals.unpriced_calls ? <p className="border-t px-3 py-2 text-[12px] text-muted-foreground">* Some calls have no price yet: the owner sets prices in the backend.</p> : null}
      </Section>
      <Section title={summary.totals.cost_usd !== null ? "Cost" : "Tokens"} description="One bar per row, largest first">
        <RankedBars
          items={summary.rows.map((r) => ({
            key: r.key,
            label: label(r.key),
            value: summary.totals.cost_usd !== null ? r.cost_usd ?? 0 : r.input_tokens + r.output_tokens,
          })).sort((a, b) => b.value - a.value)}
          format={summary.totals.cost_usd !== null ? formatMoney : (v) => formatCompact(v)}
        />
      </Section>
    </div>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string }) {
  return (
    <div className="inline-flex items-center rounded-md border p-0.5" role="radiogroup" aria-label={label}>
      <span className="px-2 text-[12px] text-muted-foreground">{label}</span>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn("rounded px-2 py-1 text-[12px]", value === o.value ? "bg-secondary font-medium" : "text-muted-foreground hover:text-foreground")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function FootprintTab({ d }: { d: UserDetailT }) {
  const f = d.footprint;
  return (
    <div className="space-y-3">
      <p className="rounded-md border border-dashed px-3 py-2 text-[13px] text-muted-foreground">{d.note} Only counts and sizes appear here: no titles, notes, files or answers.</p>
      <StatGrid>
        <StatTile label="Study sessions" value={formatInt(f.study_sessions)} sub={`${formatInt(f.youtube_sessions)} from YouTube`} />
        <StatTile label="Notes" value={formatInt(f.notes)} />
        <StatTile label="PDFs" value={formatInt(f.pdfs)} sub={formatBytes(f.pdf_bytes)} />
        <StatTile label="Word and PowerPoint files" value={formatInt(f.office_files)} />
        <StatTile label="Highlights" value={formatInt(f.highlights)} />
        <StatTile label="Sticky notes" value={formatInt(f.sticky_notes)} />
        <StatTile label="Questions answered" value={formatInt(f.answers)} />
        <StatTile label="Last session" value={<RelativeTime iso={f.last_session_at} />} />
      </StatGrid>
    </div>
  );
}

function PlanTab({ userId }: { userId: number }) {
  const plan = useQuery({ queryKey: ["user", userId, "plan"], queryFn: () => api.get<SubjectPlan>(`/users/${userId}/plan`) });
  return (
    <QueryView query={plan}>
      {(p) => <PlanHistory plan={p} />}
    </QueryView>
  );
}

export function PlanHistory({ plan }: { plan: SubjectPlan }) {
  const e = plan.effective;
  return (
    <div className="space-y-4">
      <p className="text-[13px]">
        In force: <span className="font-semibold">{e.plan.name}</span>{" "}
        <span className="text-muted-foreground">
          ({e.source === "user" ? "their own assignment" : e.source === "organization" ? "from the organisation" : "the default plan"}
          {e.ends_at ? <>, ends <RelativeTime iso={e.ends_at} /></> : null})
        </span>
      </p>
      <Section title="History" bodyClassName="p-0">
        {plan.history.length ? (
          <DataTable
            label="Plan history"
            rows={plan.history}
            rowKey={(a) => a.id}
            columns={[
              { key: "plan", header: "Plan", cell: (a) => a.plan_id },
              { key: "status", header: "Status", cell: (a) => <Pill variant={a.status === "active" ? "good" : a.status === "trial" ? "accent" : "neutral"}>{humanize(a.status)}</Pill> },
              { key: "source", header: "Source", cell: (a) => humanize(a.source) },
              { key: "from", header: "From", cell: (a) => <ExactTime iso={a.starts_at} /> },
              { key: "to", header: "Until", cell: (a) => (a.ends_at ? <ExactTime iso={a.ends_at} /> : "—") },
              { key: "by", header: "By", cell: (a) => a.assigned_by ?? "—" },
              { key: "note", header: "Note", cell: (a) => <span className="line-clamp-2 max-w-xs">{a.note ?? "—"}</span> },
            ]}
          />
        ) : (
          <EmptyState title="Never assigned a plan" />
        )}
      </Section>
    </div>
  );
}

function SupportTab({ userId }: { userId: number }) {
  const navigate = useNavigate();
  const tickets = useQuery({ queryKey: ["user", userId, "tickets"], queryFn: () => api.get<TicketList>(`/users/${userId}/tickets`) });
  return (
    <Section title="Tickets" bodyClassName="p-0">
      <QueryView query={tickets} isEmpty={(t) => !t.items.length} empty={<EmptyState title="No tickets from this person" />}>
        {(t) => (
          <DataTable
            label="Their tickets"
            rows={t.items}
            rowKey={(r) => r.id}
            onRowClick={(r) => navigate(`/tickets/${r.number}`)}
            columns={[
              { key: "n", header: "Ticket", cell: (r) => <span className="font-medium">{r.number}</span> },
              { key: "s", header: "Subject", cell: (r) => <span className="line-clamp-1">{r.subject || r.reason_label}</span> },
              { key: "st", header: "Status", cell: (r) => <TicketStatusBadge status={r.status} /> },
              { key: "u", header: "Updated", cell: (r) => <RelativeTime iso={r.updated_at} /> },
            ]}
          />
        )}
      </QueryView>
    </Section>
  );
}

function FamilyTab({ d }: { d: UserDetailT }) {
  const f = d.family;
  return (
    <div className="space-y-4">
      <StatGrid>
        <StatTile label="Guardians" value={formatInt(f.guardians_active)} sub={`${formatInt(f.guardians_revoked)} revoked`} />
        <StatTile label="Children" value={formatInt(f.children_active)} sub={`${formatInt(f.children_revoked)} revoked`} />
      </StatGrid>
      <Section title="Links" description="Who is linked, and how. The linked account's page shows only its own masked details." bodyClassName="p-0">
        {f.links.length ? (
          <DataTable
            label="Family links"
            rows={f.links}
            rowKey={(l) => l.id}
            columns={[
              { key: "rel", header: "They are", cell: (l) => (l.relation === "guardian" ? "A guardian of this account" : "A child of this account") },
              { key: "who", header: "Account", cell: (l) => <UserLink id={l.other_user_id} /> },
              { key: "origin", header: "How", cell: (l) => (l.origin === "created" ? "Made by the guardian" : "Claimed with a link code") },
              { key: "status", header: "Status", cell: (l) => <Pill variant={l.status === "active" ? "good" : "neutral"}>{humanize(l.status)}</Pill> },
              { key: "since", header: "Since", cell: (l) => <ExactTime iso={l.activated_at} /> },
              { key: "revoked", header: "Revoked", cell: (l) => (l.revoked_at ? <ExactTime iso={l.revoked_at} /> : "—") },
            ]}
          />
        ) : (
          <EmptyState title="No family links" />
        )}
      </Section>
    </div>
  );
}

function SecurityTab({ d, canEvents }: { d: UserDetailT; canEvents: boolean }) {
  const s = d.security;
  const events = useInfiniteQuery({
    queryKey: ["user", d.user.id, "auth-events"],
    queryFn: ({ pageParam }) => api.get<Page<AuthEvent>>(`/users/${d.user.id}/auth-events`, { cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: canEvents,
  });
  const rows = events.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="space-y-4">
      <StatGrid>
        <StatTile label="Failed sign-ins, 30 days" value={formatInt(s.failed_sign_ins_30d)} />
        <StatTile label="PIN locked until" value={s.locked_until ? <RelativeTime iso={s.locked_until} /> : "Not locked"} />
        <StatTile label="Refresh replays, 30 days" value={formatInt(s.replays_30d)} sub="A reused sign-in token ends every session" />
      </StatGrid>
      <Section title="Sign-in and security events" description="Newest first. Networks are hashed; the address itself is never stored." bodyClassName="p-0">
        {!canEvents ? (
          <EmptyState title="Your role can't see these events">Support and owners can.</EmptyState>
        ) : events.isPending ? (
          <LoadingBlock className="p-3" />
        ) : events.isError ? (
          <ErrorState error={events.error} onRetry={() => void events.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title="No events yet" />
        ) : (
          <>
            <AuthEventTable rows={rows} showUser={false} />
            <LoadMore hasMore={!!events.hasNextPage} loading={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()} shown={rows.length} />
          </>
        )}
      </Section>
    </div>
  );
}

export function AuthEventTable({ rows, showUser = true }: { rows: AuthEvent[]; showUser?: boolean }) {
  return (
    <DataTable
      label="Sign-in and security events"
      rows={rows}
      rowKey={(e) => e.id}
      columns={[
        { key: "at", header: "When", cell: (e) => <ExactTime iso={e.created_at} /> },
        {
          key: "kind",
          header: "What",
          cell: (e) => (
            <Pill variant={e.kind === "sign_in" ? "good" : e.kind === "sign_in_failed" || e.kind === "refresh_replay" || e.kind === "pin_locked" ? "bad" : "neutral"}>
              {humanize(e.kind)}
            </Pill>
          ),
        },
        ...(showUser ? [{ key: "user", header: "Account", cell: (e: AuthEvent) => <UserLink id={e.user_id} /> }] : []),
        { key: "method", header: "Method", cell: (e) => providerLabel(e.method) },
        { key: "reason", header: "Reason", cell: (e) => (e.reason ? humanize(e.reason) : "—") },
        { key: "where", header: "Browser", cell: (e) => e.ua_family ?? "—" },
        { key: "country", header: "Country", cell: (e) => e.country ?? "—" },
        { key: "net", header: "Network", cell: (e) => <code className="text-[11px] text-muted-foreground">{e.ip_prefix_hash?.slice(0, 8) ?? "—"}</code> },
      ]}
    />
  );
}

function AppActivityTab({ userId }: { userId: number }) {
  const [range] = useRange("30d");
  const events = useInfiniteQuery({
    queryKey: ["analytics", "events", { user_id: userId, from: range.from, to: range.to }],
    queryFn: ({ pageParam }) => api.get<Page<AnalyticsEvent>>("/analytics/events", { user_id: userId, from: range.from, to: range.to, cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
  });
  const rows = events.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <RangePicker />
        <p className="text-[12px] text-muted-foreground">Pages opened, actions taken and errors hit in the app. Never what was written or studied.</p>
      </div>
      <Section bodyClassName="p-0">
        {events.isPending ? (
          <LoadingBlock className="p-3" />
        ) : events.isError && !events.data ? (
          <ErrorState error={events.error} onRetry={() => void events.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title="Nothing in this range" />
        ) : (
          <>
            <EventTable rows={rows} showUser={false} />
            <LoadMore hasMore={!!events.hasNextPage} loading={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()} shown={rows.length} />
          </>
        )}
      </Section>
    </div>
  );
}

export function EventTable({ rows, showUser = true }: { rows: AnalyticsEvent[]; showUser?: boolean }) {
  return (
    <DataTable
      label="App activity"
      rows={rows}
      rowKey={(e) => e.id}
      columns={[
        { key: "at", header: "When", cell: (e) => <ExactTime iso={e.created_at} /> },
        {
          key: "kind",
          header: "Kind",
          cell: (e) => <Pill variant={e.kind === "error" ? "bad" : e.kind === "action" ? "accent" : "neutral"}>{e.kind === "view" ? "Page" : humanize(e.kind)}</Pill>,
        },
        ...(showUser ? [{ key: "user", header: "Account", cell: (e: AnalyticsEvent) => <UserLink id={e.user_id} /> }] : []),
        { key: "name", header: "What", cell: (e) => <span className={cn("block max-w-md break-words", e.kind === "error" && "font-mono text-[12px]")}>{e.name}</span> },
        { key: "path", header: "Page", cell: (e) => <span className="block max-w-[16rem] truncate text-muted-foreground" title={e.path ?? undefined}>{e.path ?? "—"}</span> },
        {
          key: "utm",
          header: "Came from",
          cell: (e) => (e.utm_source ? <span className="text-muted-foreground">{[e.utm_source, e.utm_medium, e.utm_campaign].filter(Boolean).join(" / ")}</span> : "—"),
        },
      ]}
    />
  );
}

function ActionsTab({ d, canSignOut, canSetActive }: { d: UserDetailT; canSignOut: boolean; canSetActive: boolean }) {
  const u = d.user;
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["user", u.id] });
    void queryClient.invalidateQueries({ queryKey: ["users"] });
  };
  const deleted = u.status === "deleted";
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {canSignOut ? (
        <Section title="Sign out everywhere" description="Ends every live session on every device.">
          <p className="mb-3 text-[13px] text-muted-foreground">
            It takes effect within a minute: the app keeps each sign-in's check for up to 60 seconds. Their data and account are untouched; they can sign in again.
          </p>
          <ReasonDialog
            trigger={
              <Button variant="outline" disabled={deleted}>
                <LogOut /> Sign out everywhere
              </Button>
            }
            title="Sign out everywhere"
            description={`Ends all ${formatInt(u.live_sessions)} live sessions of account #${u.id}, within a minute.`}
            confirmLabel="Sign out everywhere"
            onConfirm={async (reason) => {
              const r = await api.post<{ sessions_ended: number }>(`/users/${u.id}/sign-out-everywhere`, { reason });
              toast(`Signed out: ${formatInt(r.sessions_ended)} sessions ended`);
              refresh();
            }}
          />
        </Section>
      ) : null}
      {canSetActive ? (
        <Section title={u.status === "deactivated" ? "Reactivate the account" : "Deactivate the account"} description="Owners only.">
          <p className="mb-3 text-[13px] text-muted-foreground">
            {u.status === "deactivated"
              ? "They can sign in again. Nothing was deleted while it was off."
              : "They are signed out and can't sign in until it is reactivated. Nothing is deleted."}
          </p>
          {deleted ? (
            <p className="text-[13px] text-muted-foreground">This account was deleted; there is nothing to change.</p>
          ) : u.status === "deactivated" ? (
            <ReasonDialog
              trigger={
                <Button variant="outline">
                  <Power /> Reactivate
                </Button>
              }
              title="Reactivate this account"
              description={`Account #${u.id} will be able to sign in again.`}
              confirmLabel="Reactivate"
              onConfirm={async (reason) => {
                await api.post(`/users/${u.id}/reactivate`, { reason });
                toast("Reactivated");
                refresh();
              }}
            />
          ) : (
            <ReasonDialog
              trigger={
                <Button variant="destructive">
                  <PowerOff /> Deactivate
                </Button>
              }
              title="Deactivate this account"
              description={`Account #${u.id} is signed out within a minute and can't sign in until reactivated.`}
              confirmLabel="Deactivate"
              destructive
              onConfirm={async (reason) => {
                await api.post(`/users/${u.id}/deactivate`, { reason });
                toast("Deactivated");
                refresh();
              }}
            />
          )}
        </Section>
      ) : null}
      <div className="lg:col-span-2">
        <AuditBadge text="Each of these writes one row to the audit log: who, what, which account and why." />
      </div>
    </div>
  );
}
