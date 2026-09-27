/**
 * A ticket (6.4.4): the conversation, the reply box, and what support needs beside it:
 * status, priority, assignee and tags; who wrote it (masked), their plan and recent
 * usage; and what their page knew when they wrote (browser, app version, page).
 * Everything the person wrote is shown as plain text, never as HTML.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronDown, ChevronUp, MessageSquareText, Send, StickyNote } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Pill, PriorityBadge, TicketStatusBadge } from "@/components/badges";
import { Identity } from "@/components/Identity";
import { Facts, Section } from "@/components/Page";
import { EmptyState, LoadingBlock, QueryView } from "@/components/states";
import { ExactTime, RelativeTime } from "@/components/Time";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { formatCompact, formatMoney, ticketIdFromNumber } from "@/lib/format";
import { useLiveTickets } from "@/lib/live";
import { useCan, useMe } from "@/lib/me";
import { SAVED_REPLIES, fillReply } from "@/lib/savedReplies";
import type { TicketDetail as TicketDetailT, TicketMessage, TicketPriority, TicketRow, TicketStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

import { QUEUE_ORDER_KEY } from "./Tickets";

const STATUSES: { value: TicketStatus; label: string }[] = [
  { value: "open", label: "New" },
  { value: "waiting_on_us", label: "Waiting on us" },
  { value: "waiting_on_user", label: "Waiting on user" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

function queueOrder(): string[] {
  try {
    const raw = JSON.parse(sessionStorage.getItem(QUEUE_ORDER_KEY) ?? "[]");
    return Array.isArray(raw) ? raw.map(String) : [];
  } catch {
    return [];
  }
}

export default function TicketDetail() {
  const { number = "" } = useParams();
  const ticketId = ticketIdFromNumber(number);
  const navigate = useNavigate();
  const { markRead } = useLiveTickets();
  const ticket = useQuery({
    queryKey: ["ticket", ticketId],
    queryFn: () => api.get<TicketDetailT>(`/tickets/${ticketId}`),
    enabled: ticketId !== null,
  });

  useEffect(() => {
    if (ticketId !== null) markRead(ticketId);
  }, [ticketId, markRead, ticket.dataUpdatedAt]);

  // J and K walk the list the inbox last showed.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.closest("[role=dialog],[role=listbox],[role=menu]"))) return;
      if (e.key !== "j" && e.key !== "k") return;
      const order = queueOrder();
      const here = order.findIndex((n) => ticketIdFromNumber(n) === ticketId);
      const next = order[here + (e.key === "j" ? 1 : -1)];
      if (here >= 0 && next) {
        e.preventDefault();
        navigate(`/tickets/${next}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ticketId, navigate]);

  if (ticketId === null) return <EmptyState title="That isn't a ticket number">Ticket numbers look like AN-0042.</EmptyState>;
  return (
    <div>
      <Link to="/tickets" className="mb-2 inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Tickets
      </Link>
      <QueryView query={ticket} loading={<LoadingBlock rows={8} />}>
        {(t) => <Ticket t={t} />}
      </QueryView>
    </div>
  );
}

function Ticket({ t }: { t: TicketDetailT }) {
  const canWrite = useCan("tickets.write");
  const order = queueOrder();
  const here = order.indexOf(t.ticket.number);
  const navigate = useNavigate();
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12px] text-muted-foreground">
            {t.ticket.number} · {t.ticket.reason_label}
          </p>
          <h1 className="mt-0.5 text-xl font-semibold tracking-tight">{t.ticket.subject || t.ticket.reason_label}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
            <TicketStatusBadge status={t.ticket.status} />
            <PriorityBadge priority={t.ticket.priority} />
            <span>
              Opened <RelativeTime iso={t.ticket.created_at} />
            </span>
            {t.ticket.tags.map((tag) => (
              <Pill key={tag}>#{tag}</Pill>
            ))}
          </div>
        </div>
        {here >= 0 ? (
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" disabled={here <= 0} onClick={() => navigate(`/tickets/${order[here - 1]}`)} title="Previous (K)">
              <ChevronUp />
            </Button>
            <Button variant="outline" size="sm" disabled={here >= order.length - 1} onClick={() => navigate(`/tickets/${order[here + 1]}`)} title="Next (J)">
              <ChevronDown />
            </Button>
          </div>
        ) : null}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-4">
          <Conversation t={t} />
          {canWrite ? <ReplyBox t={t} /> : <p className="text-[13px] text-muted-foreground">Your role can read tickets but not answer them.</p>}
        </div>
        <aside className="space-y-4">
          <Controls t={t} canWrite={canWrite} />
          <PersonPanel t={t} />
          <ContextPanel t={t} />
        </aside>
      </div>
    </div>
  );
}

function Conversation({ t }: { t: TicketDetailT }) {
  return (
    <ol className="space-y-3" aria-label="Conversation">
      {t.messages.map((m) => (
        <MessageItem key={m.id} m={m} firstName={t.user.identity.first_name} />
      ))}
    </ol>
  );
}

function MessageItem({ m, firstName }: { m: TicketMessage; firstName: string }) {
  if (m.author === "system") {
    return (
      <li className="text-center text-[12px] text-muted-foreground">
        {m.body} · <RelativeTime iso={m.created_at} />
      </li>
    );
  }
  const staff = m.author === "staff";
  return (
    <li
      className={cn(
        "rounded-lg border px-4 py-3",
        m.internal ? "border-dashed border-[hsl(var(--warning)/0.5)] bg-[hsl(var(--warning)/0.07)]" : staff ? "bg-muted/40" : "bg-card",
      )}
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[12px]">
        <span className="font-semibold">{staff ? m.staff_email ?? "Staff" : firstName || "The person"}</span>
        <span className="text-muted-foreground">{staff ? "Support" : "Wrote"}</span>
        {m.internal ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-[hsl(var(--warning)/0.15)] px-2 text-[11px] font-medium text-[hsl(var(--warning))]">
            <StickyNote className="size-3" /> Only staff see this
          </span>
        ) : null}
        <span className="ml-auto text-muted-foreground">
          <ExactTime iso={m.created_at} />
        </span>
      </div>
      {/* Plain text only: whitespace kept, never parsed as HTML or Markdown. */}
      <p className="whitespace-pre-wrap break-words text-[13px] leading-relaxed">{m.body}</p>
    </li>
  );
}

function ReplyBox({ t }: { t: TicketDetailT }) {
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [internal, setInternal] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (params.get("reply") === "1") {
      box.current?.focus();
      setParams((p) => { const n = new URLSearchParams(p); n.delete("reply"); return n; }, { replace: true });
    }
  }, [params, setParams]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (e.key !== "r" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable || target.closest("[role=dialog],[role=menu],[role=listbox]"))) return;
      e.preventDefault();
      box.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const send = useMutation({
    mutationFn: () => api.post<TicketMessage>(`/tickets/${t.ticket.id}/messages`, { body: body.trim(), internal }),
    onSuccess: async () => {
      toast(internal ? "Note added" : "Reply sent");
      setBody("");
      await queryClient.invalidateQueries({ queryKey: ["ticket", t.ticket.id] });
      void queryClient.invalidateQueries({ queryKey: ["tickets"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const ok = body.trim().length > 0 && body.length <= 10_000;
  return (
    <form
      className={cn("rounded-lg border p-3", internal && "border-dashed border-[hsl(var(--warning)/0.6)] bg-[hsl(var(--warning)/0.05)]")}
      onSubmit={(e) => {
        e.preventDefault();
        if (ok && !send.isPending) send.mutate();
      }}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <Label htmlFor="reply" className="text-[13px]">
          {internal ? "Internal note: only staff see it" : `Reply to ${t.user.identity.first_name || "the person"}`}
        </Label>
        <div className="flex items-center gap-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="ghost" size="sm" className="h-7">
                <MessageSquareText /> Saved replies
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuLabel>Insert, then edit before sending</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {SAVED_REPLIES.map((r) => (
                <DropdownMenuItem
                  key={r.id}
                  onSelect={() => {
                    setInternal(false);
                    setBody(fillReply(r.body, { first_name: t.user.identity.first_name, number: t.ticket.number }));
                    setTimeout(() => box.current?.focus(), 0);
                  }}
                >
                  {r.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <label className="flex items-center gap-2 text-[12px]">
            <Switch checked={internal} onCheckedChange={setInternal} aria-label="Internal note" />
            Internal note
          </label>
        </div>
      </div>
      <Textarea
        id="reply"
        ref={box}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={6}
        maxLength={10_000}
        placeholder={internal ? "What the next person should know" : "Write the reply they'll see under their ticket"}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && ok && !send.isPending) {
            e.preventDefault();
            send.mutate();
          }
        }}
      />
      <div className="mt-2 flex items-center justify-between gap-2 text-[12px] text-muted-foreground">
        <span>{internal ? "Doesn't change the status." : "Sending moves it to Waiting on user."} Ctrl+Enter sends.</span>
        <Button type="submit" size="sm" disabled={!ok || send.isPending}>
          {internal ? <StickyNote /> : <Send />} {send.isPending ? "Sending…" : internal ? "Add note" : "Send reply"}
        </Button>
      </div>
    </form>
  );
}

function Controls({ t, canWrite }: { t: TicketDetailT; canWrite: boolean }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const [tags, setTags] = useState(t.ticket.tags.join(", "));
  useEffect(() => setTags(t.ticket.tags.join(", ")), [t.ticket.tags]);
  const update = useMutation({
    mutationFn: (changes: Partial<{ status: TicketStatus; priority: TicketPriority; assignee_email: string | null; tags: string[] }>) =>
      api.patch<TicketRow>(`/tickets/${t.ticket.id}`, changes),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["ticket", t.ticket.id] });
      void queryClient.invalidateQueries({ queryKey: ["tickets"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const parsedTags = tags
    .split(",")
    .map((x) => x.trim().toLowerCase().replace(/\s+/g, "-"))
    .filter(Boolean);
  return (
    <Section title="Ticket">
      <div className="space-y-3 text-[13px]">
        <div className="grid grid-cols-[5.5rem_1fr] items-center gap-2">
          <Label>Status</Label>
          <Select value={t.ticket.status} disabled={!canWrite || update.isPending} onValueChange={(v) => update.mutate({ status: v as TicketStatus })}>
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUSES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Label>Priority</Label>
          <Select value={t.ticket.priority} disabled={!canWrite || update.isPending} onValueChange={(v) => update.mutate({ priority: v as TicketPriority })}>
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(["urgent", "high", "normal", "low"] as const).map((p) => (
                <SelectItem key={p} value={p}>
                  {p.charAt(0).toUpperCase() + p.slice(1)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Label>Assignee</Label>
          <div className="flex min-w-0 items-center gap-1">
            <span className="min-w-0 flex-1 truncate">{t.ticket.assignee_email ?? <span className="text-muted-foreground">Nobody</span>}</span>
            {canWrite && t.ticket.assignee_email !== me.email ? (
              <Button variant="outline" size="sm" className="h-7 px-2" disabled={update.isPending} onClick={() => update.mutate({ assignee_email: me.email })}>
                Take it
              </Button>
            ) : null}
            {canWrite && t.ticket.assignee_email ? (
              <Button variant="ghost" size="sm" className="h-7 px-2" disabled={update.isPending} onClick={() => update.mutate({ assignee_email: null })}>
                Unassign
              </Button>
            ) : null}
          </div>
          <Label htmlFor="tags">Tags</Label>
          <form
            className="flex gap-1"
            onSubmit={(e) => {
              e.preventDefault();
              update.mutate({ tags: parsedTags });
            }}
          >
            <Input id="tags" value={tags} onChange={(e) => setTags(e.target.value)} disabled={!canWrite} placeholder="safari, audio" className="h-8" />
            {canWrite && parsedTags.join(",") !== t.ticket.tags.join(",") ? (
              <Button size="sm" className="h-8" type="submit" disabled={update.isPending}>
                Save
              </Button>
            ) : null}
          </form>
        </div>
        {t.closed_at ? (
          <p className="text-[12px] text-muted-foreground">
            Closed <RelativeTime iso={t.closed_at} />
          </p>
        ) : null}
      </div>
    </Section>
  );
}

function PersonPanel({ t }: { t: TicketDetailT }) {
  const u = t.user;
  return (
    <Section title="From" description="Masked. Their page has more, and an audited Reveal.">
      <Identity id={u.id} identity={u.identity} kind={u.kind} />
      <Facts
        className="mt-3"
        items={[
          ["Account", <Link key="a" to={`/users/${u.id}`} className="underline">#{u.id}</Link>],
          ["Plan", u.plan ? `${u.plan.name}${u.plan.status === "trial" ? " (trial)" : ""}` : "—"],
          ["Organisation", u.organization?.name ?? "—"],
          ["Last seen", <RelativeTime key="s" iso={u.last_seen_at} />],
          ["AI use, 30 days", `${formatCompact(u.usage_30d.tokens)} tokens · ${formatMoney(u.usage_30d.cost_usd)}`],
        ]}
      />
    </Section>
  );
}

function ContextPanel({ t }: { t: TicketDetailT }) {
  const c = t.context ?? {};
  return (
    <Section title="What the page knew" description="Sent with the ticket. A session id shows which session, never what's in it.">
      <Facts
        items={[
          ["Page", <span key="p" className="break-all">{t.page_url ?? "—"}</span>],
          ["Came from", c.from ?? "—"],
          ["Browser", c.browser ?? "—"],
          ["Language", c.language ?? "—"],
          ["Screen", c.viewport ?? "—"],
          ["Time zone", c.timezone ?? "—"],
          ["App version", c.app_version ?? "—"],
          ["Session", <code key="s" className="break-all text-[12px]">{c.session_id ?? "—"}</code>],
        ]}
      />
    </Section>
  );
}
