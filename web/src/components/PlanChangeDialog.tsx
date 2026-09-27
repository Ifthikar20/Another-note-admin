/**
 * Change the plan of a person or an organisation (owner only). The new assignment
 * replaces the current one; "Remove" ends the subject's own assignment, so a person falls
 * back to their organisation's plan, then the default. The note is the audit reason.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { usePlans } from "@/lib/queries";
import type { Assignment } from "@/lib/types";

import { AuditBadge } from "./AuditBadge";

export function PlanChangeDialog({
  subject,
  id,
  currentPlanId,
  hasOwnAssignment,
}: {
  subject: "user" | "org";
  id: number;
  currentPlanId?: string;
  hasOwnAssignment: boolean;
}) {
  const plans = usePlans();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [planId, setPlanId] = useState(currentPlanId ?? "");
  const [status, setStatus] = useState<"active" | "trial" | "canceled">("active");
  const [endsAt, setEndsAt] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const removing = status === "canceled";
  const ok = note.trim().length >= 3 && (removing ? hasOwnAssignment : !!planId);
  const path = subject === "user" ? `/users/${id}/plan` : `/orgs/${id}/plan`;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setPlanId(currentPlanId ?? "");
          setStatus("active");
          setEndsAt("");
          setNote("");
          setError(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-7">
          Change plan
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!ok || busy) return;
            setBusy(true);
            setError(null);
            try {
              await api.put<Assignment>(path, {
                plan_id: removing ? currentPlanId || planId : planId,
                status,
                ends_at: endsAt ? `${endsAt}T23:59:59Z` : null,
                note: note.trim(),
              });
              toast(removing ? "Plan assignment removed" : "Plan changed");
              setOpen(false);
              await queryClient.invalidateQueries({ queryKey: subject === "user" ? ["user", id] : ["org", id] });
              void queryClient.invalidateQueries({ queryKey: [subject === "user" ? "users" : "orgs"] });
              void queryClient.invalidateQueries({ queryKey: ["plans"] });
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>Change the plan</DialogTitle>
            <DialogDescription>
              {subject === "user"
                ? "The person's own plan takes precedence over their organisation's. Limits are recorded now and enforced in a later phase."
                : "Members without a plan of their own get this one."}
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>What</Label>
                <Select value={status} onValueChange={(v) => setStatus(v as typeof status)}>
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Assign a plan</SelectItem>
                    <SelectItem value="trial">Start a trial</SelectItem>
                    {hasOwnAssignment ? <SelectItem value="canceled">Remove their own plan</SelectItem> : null}
                  </SelectContent>
                </Select>
              </div>
              {!removing ? (
                <div className="space-y-1.5">
                  <Label>Plan</Label>
                  <Select value={planId} onValueChange={setPlanId}>
                    <SelectTrigger className="h-8">
                      <SelectValue placeholder="Choose a plan" />
                    </SelectTrigger>
                    <SelectContent>
                      {(plans.data?.items ?? [])
                        .filter((p) => p.is_active)
                        .map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.name}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}
            </div>
            {!removing ? (
              <div className="space-y-1.5">
                <Label htmlFor="plan-ends">Ends (optional, UTC day)</Label>
                <Input id="plan-ends" type="date" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} className="h-8 w-44" />
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor="plan-note">Note</Label>
              <Textarea id="plan-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={500} placeholder="Why: the audit log keeps it" />
            </div>
          </div>
          {error ? (
            <p role="alert" className="mt-2 text-[13px] text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter className="mt-4 items-center gap-2 sm:justify-between">
            <AuditBadge />
            <div className="flex gap-2">
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!ok || busy} variant={removing ? "destructive" : "default"}>
                {busy ? "Saving…" : removing ? "Remove" : "Save"}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
