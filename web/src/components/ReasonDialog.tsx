/**
 * Every privileged action asks why (at least 5 characters, as the database function
 * requires) and says it is audited. The reason goes into the audit log with the actor.
 */
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api";

import { AuditBadge } from "./AuditBadge";

export const MIN_REASON = 5;

export function ReasonDialog({
  trigger,
  title,
  description,
  confirmLabel,
  destructive,
  onConfirm,
  placeholder = "Why, in a sentence (the ticket number helps)",
}: {
  trigger: ReactNode;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  onConfirm: (reason: string) => Promise<void>;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ok = reason.trim().length >= MIN_REASON;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setReason("");
          setError(null);
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!ok || busy) return;
            setBusy(true);
            setError(null);
            try {
              await onConfirm(reason.trim());
              setOpen(false);
              setReason("");
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription asChild>
              <div className="text-[13px]">{description}</div>
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-1.5">
            <Label htmlFor="reason">Reason</Label>
            <Textarea id="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder={placeholder} rows={3} maxLength={500} autoFocus />
            <p className="text-[12px] text-muted-foreground">At least {MIN_REASON} characters.</p>
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
              <Button type="submit" variant={destructive ? "destructive" : "default"} disabled={!ok || busy}>
                {busy ? "Working…" : confirmLabel}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
