import { badgeVariants } from "@/components/ui/badge";
import { humanize } from "@/lib/format";
import type { TicketPriority, TicketStatus, UserStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const tone = {
  neutral: "border-border bg-secondary text-secondary-foreground",
  accent: "border-transparent bg-accent text-accent-foreground",
  good: "border-transparent bg-[hsl(var(--success)/0.12)] text-[hsl(var(--success))]",
  warn: "border-transparent bg-[hsl(var(--warning)/0.14)] text-[hsl(var(--warning))]",
  bad: "border-transparent bg-destructive/10 text-destructive",
  strong: "border-transparent bg-primary text-primary-foreground",
} as const;

export function Pill({ children, variant = "neutral", className, title }: { children: React.ReactNode; variant?: keyof typeof tone; className?: string; title?: string }) {
  // A span, so a pill can sit inside a line of text.
  return (
    <span title={title} className={cn(badgeVariants({ variant: "outline" }), "whitespace-nowrap rounded-full px-2 py-0 text-[11px] font-medium leading-5", tone[variant], className)}>
      {children}
    </span>
  );
}

const TICKET_STATUS: Record<TicketStatus, [string, keyof typeof tone]> = {
  open: ["New", "accent"],
  waiting_on_us: ["Waiting on us", "warn"],
  waiting_on_user: ["Waiting on user", "neutral"],
  resolved: ["Resolved", "good"],
  closed: ["Closed", "neutral"],
};

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  const [label, variant] = TICKET_STATUS[status] ?? [humanize(status), "neutral"];
  return <Pill variant={variant}>{label}</Pill>;
}

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  if (priority === "normal") return <span className="text-xs text-muted-foreground">Normal</span>;
  const variant = priority === "urgent" ? "bad" : priority === "high" ? "warn" : "neutral";
  return <Pill variant={variant}>{humanize(priority)}</Pill>;
}

export function UserStatusBadge({ status }: { status: UserStatus }) {
  if (status === "active") return <Pill variant="good">Active</Pill>;
  if (status === "deactivated") return <Pill variant="bad">Deactivated</Pill>;
  return <Pill variant="neutral">Deleted</Pill>;
}

const FLAG_LABELS: Record<string, [string, keyof typeof tone, string]> = {
  deactivated: ["Deactivated", "bad", "Signed out and unable to sign in"],
  deleted: ["Deleted", "neutral", "The account was deleted"],
  locked: ["PIN locked", "warn", "Too many wrong PINs; it unlocks by itself"],
  demo: ["Demo", "accent", "A demo account"],
  child: ["Child", "accent", "A child profile made by a guardian (no email)"],
  child_linked: ["Has guardian", "neutral", "A guardian is linked to this account"],
  guardian: ["Guardian", "neutral", "Guardian of at least one child"],
};

export function FlagBadges({ flags, hide = [] }: { flags: string[]; hide?: string[] }) {
  const shown = flags.filter((f) => !hide.includes(f));
  if (!shown.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {shown.map((f) => {
        const [label, variant, title] = FLAG_LABELS[f] ?? [humanize(f), "neutral" as const, f];
        return (
          <Pill key={f} variant={variant} title={title}>
            {label}
          </Pill>
        );
      })}
    </span>
  );
}

export function RoleBadge({ role }: { role: string }) {
  return <Pill variant={role === "owner" ? "strong" : role === "support" ? "accent" : "neutral"}>{humanize(role)}</Pill>;
}
