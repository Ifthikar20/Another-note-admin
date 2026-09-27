/**
 * Plans (6.4.6): the entitlement bundles, their limits, and how many people and schools
 * are on each. Owners create and edit them. Limits are recorded now and enforced in a
 * later phase; a blank limit means unlimited.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { AuditBadge } from "@/components/AuditBadge";
import { Pill } from "@/components/badges";
import { PageHeader } from "@/components/Page";
import { EmptyState, LoadingBlock, QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { formatInt, formatMoney } from "@/lib/format";
import { useCan } from "@/lib/me";
import { usePlans } from "@/lib/queries";
import type { Plan, PlanLimits } from "@/lib/types";

const NUMBER_LIMITS: { key: keyof PlanLimits; label: string; unit: string }[] = [
  { key: "monthly_ai_tokens", label: "AI tokens a month", unit: "tokens" },
  { key: "monthly_ai_cost_usd", label: "AI cost a month", unit: "USD" },
  { key: "monthly_tts_characters", label: "Voice characters a month", unit: "characters" },
  { key: "monthly_transcription_minutes", label: "Transcription a month", unit: "minutes" },
  { key: "max_upload_mb", label: "Largest upload", unit: "MB" },
  { key: "max_study_sessions", label: "Study sessions", unit: "sessions" },
  { key: "family_seats", label: "Family seats", unit: "children" },
];
const SWITCHES: { key: keyof PlanLimits; label: string }[] = [
  { key: "teach_mode", label: "Teach mode" },
  { key: "pictures", label: "Board pictures" },
  { key: "youtube_import", label: "YouTube import" },
];

function limitText(limits: PlanLimits, key: keyof PlanLimits, unit: string): string {
  const v = limits[key];
  if (v === null || v === undefined) return "Unlimited";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return unit === "USD" ? formatMoney(v) : `${formatInt(v)} ${unit}`;
}

export default function Plans() {
  const plans = usePlans();
  const canWrite = useCan("plans.write");
  const [editing, setEditing] = useState<Plan | "new" | null>(null);
  return (
    <div>
      <PageHeader
        title="Plans"
        description="What each plan allows. A person's own plan comes first, then their organisation's, then the default. Limits are recorded now; enforcing them comes later."
        actions={
          canWrite ? (
            <Button size="sm" onClick={() => setEditing("new")}>
              <Plus /> New plan
            </Button>
          ) : null
        }
      />
      <QueryView query={plans} loading={<LoadingBlock rows={6} />} isEmpty={(p) => !p.items.length} empty={<EmptyState title="No plans yet" />}>
        {(p) => (
          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
            {p.items.map((plan) => (
              <article key={plan.id} className="flex flex-col rounded-lg border bg-card">
                <header className="flex items-start justify-between gap-2 border-b px-4 py-3">
                  <div>
                    <h2 className="flex items-center gap-2 text-sm font-semibold">
                      {plan.name}
                      {plan.is_default ? <Pill variant="accent">Default</Pill> : null}
                      {!plan.is_active ? <Pill>Off</Pill> : null}
                    </h2>
                    <p className="mt-0.5 text-[12px] text-muted-foreground">
                      <code>{plan.id}</code> · {plan.price_cents !== null ? `${formatMoney(plan.price_cents / 100)} ${plan.currency ?? ""} a ${plan.interval ?? "period"}` : "No price"}
                    </p>
                  </div>
                  {canWrite ? (
                    <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setEditing(plan)} aria-label={`Edit ${plan.name}`}>
                      <Pencil />
                    </Button>
                  ) : null}
                </header>
                <div className="flex-1 px-4 py-3">
                  {plan.description ? <p className="mb-3 text-[13px]">{plan.description}</p> : null}
                  <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-[12px]">
                    {NUMBER_LIMITS.map((l) => (
                      <div key={l.key} className="contents">
                        <dt className="text-muted-foreground">{l.label}</dt>
                        <dd className="num text-right">{limitText(plan.limits, l.key, l.unit)}</dd>
                      </div>
                    ))}
                    {SWITCHES.map((l) => (
                      <div key={l.key} className="contents">
                        <dt className="text-muted-foreground">{l.label}</dt>
                        <dd className="text-right">{limitText(plan.limits, l.key, "")}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
                <footer className="border-t px-4 py-2 text-[12px] text-muted-foreground">
                  <Link to={`/users?plan=${encodeURIComponent(plan.id)}`} className="hover:underline">
                    {formatInt(plan.assignments.active)} assigned · {formatInt(plan.assignments.trial)} on trial
                  </Link>
                  {plan.is_default ? " · and everyone without another plan" : ""}
                </footer>
              </article>
            ))}
          </div>
        )}
      </QueryView>
      {editing ? <PlanDialog plan={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
    </div>
  );
}

function PlanDialog({ plan, onClose }: { plan: Plan | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [id, setId] = useState(plan?.id ?? "");
  const [name, setName] = useState(plan?.name ?? "");
  const [description, setDescription] = useState(plan?.description ?? "");
  const [active, setActive] = useState(plan?.is_active ?? true);
  const [isDefault, setIsDefault] = useState(plan?.is_default ?? false);
  const [price, setPrice] = useState(plan?.price_cents !== null && plan?.price_cents !== undefined ? String(plan.price_cents / 100) : "");
  const [billing, setBilling] = useState<"month" | "year" | "none">(plan?.interval ?? "none");
  const [limits, setLimits] = useState<Record<string, string>>(() =>
    Object.fromEntries(NUMBER_LIMITS.map((l) => [l.key, plan?.limits[l.key] !== null && plan?.limits[l.key] !== undefined ? String(plan.limits[l.key]) : ""])),
  );
  const [switches, setSwitches] = useState<Record<string, "unset" | "yes" | "no">>(() =>
    Object.fromEntries(SWITCHES.map((l) => [l.key, plan?.limits[l.key] === true ? "yes" : plan?.limits[l.key] === false ? "no" : "unset"])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const idOk = /^[a-z0-9][a-z0-9_-]{0,39}$/.test(id);
  const numbersOk = Object.values(limits).every((v) => v === "" || (Number.isFinite(Number(v)) && Number(v) >= 0));
  const ok = (plan || idOk) && name.trim() && numbersOk && (price === "" || Number(price) >= 0);

  const body = () => {
    const out: PlanLimits = {};
    for (const l of NUMBER_LIMITS) {
      const v = limits[l.key];
      (out as Record<string, unknown>)[l.key] = v === "" ? null : l.key === "monthly_ai_cost_usd" ? Number(v) : Math.round(Number(v));
    }
    for (const l of SWITCHES) (out as Record<string, unknown>)[l.key] = switches[l.key] === "unset" ? null : switches[l.key] === "yes";
    return {
      name: name.trim(),
      description: description.trim(),
      is_active: active,
      is_default: isDefault,
      limits: out,
      price_cents: price === "" ? null : Math.round(Number(price) * 100),
      currency: price === "" ? null : "USD",
      interval: billing === "none" ? null : billing,
    };
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!ok || busy) return;
            setBusy(true);
            setError(null);
            try {
              if (plan) await api.patch<Plan>(`/plans/${plan.id}`, body());
              else await api.post<Plan>("/plans", { id, ...body() });
              toast(plan ? "Plan saved" : "Plan created");
              await queryClient.invalidateQueries({ queryKey: ["plans"] });
              onClose();
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>{plan ? `Edit ${plan.name}` : "New plan"}</DialogTitle>
            <DialogDescription>Leave a limit blank for unlimited. Nothing is enforced yet: this records what each plan will allow.</DialogDescription>
          </DialogHeader>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="plan-id">Id</Label>
              <Input id="plan-id" value={id} onChange={(e) => setId(e.target.value.toLowerCase())} disabled={!!plan} placeholder="plus" />
              {!plan && id && !idOk ? <p className="text-[12px] text-destructive">Lower-case letters, digits, - and _.</p> : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="plan-name">Name</Label>
              <Input id="plan-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="plan-desc">Description</Label>
              <Textarea id="plan-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} maxLength={500} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="plan-price">Price (USD, optional)</Label>
              <Input id="plan-price" value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" placeholder="None" />
            </div>
            <div className="space-y-1.5">
              <Label>Billed</Label>
              <Select value={billing} onValueChange={(v) => setBilling(v as typeof billing)}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Not billed</SelectItem>
                  <SelectItem value="month">Monthly</SelectItem>
                  <SelectItem value="year">Yearly</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {NUMBER_LIMITS.map((l) => (
              <div key={l.key} className="space-y-1.5">
                <Label htmlFor={`limit-${l.key}`}>
                  {l.label} <span className="text-muted-foreground">({l.unit})</span>
                </Label>
                <Input
                  id={`limit-${l.key}`}
                  value={limits[l.key]}
                  onChange={(e) => setLimits((c) => ({ ...c, [l.key]: e.target.value }))}
                  inputMode="decimal"
                  placeholder="Unlimited"
                />
              </div>
            ))}
            {SWITCHES.map((l) => (
              <div key={l.key} className="space-y-1.5">
                <Label>{l.label}</Label>
                <Select value={switches[l.key]} onValueChange={(v) => setSwitches((c) => ({ ...c, [l.key]: v as "unset" | "yes" | "no" }))}>
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="unset">Not set (allowed)</SelectItem>
                    <SelectItem value="yes">Allowed</SelectItem>
                    <SelectItem value="no">Not allowed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            ))}
            <label className="col-span-2 flex items-center gap-2 text-[13px]">
              <Checkbox checked={active} onCheckedChange={(v) => setActive(v === true)} disabled={plan?.is_default} /> Active (can be assigned)
            </label>
            <label className="col-span-2 flex items-center gap-2 text-[13px]">
              <Checkbox checked={isDefault} onCheckedChange={(v) => setIsDefault(v === true)} disabled={plan?.is_default} /> The default plan (for everyone without another)
            </label>
          </div>
          {error ? (
            <p role="alert" className="mt-2 text-[13px] text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter className="mt-4 items-center gap-2 sm:justify-between">
            <AuditBadge text="Recorded in the audit log: plan.create or plan.update, with your name." />
            <div className="flex gap-2">
              <Button type="button" variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={!ok || busy}>
                {busy ? "Saving…" : "Save"}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
