/**
 * An email address, masked, with a Reveal button for the roles allowed to (owner,
 * support). Revealing asks for a reason (and optionally the ticket it is for), is audited
 * by the admin API, and shows the address for 60 seconds before masking it again. The
 * address is kept only in this component's state: never in the query cache, never in the
 * URL, and gone when the page changes or the screen locks.
 */
import { Copy, Eye, EyeOff } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { ticketIdFromNumber } from "@/lib/format";
import { useCan } from "@/lib/me";
import type { RevealedEmail } from "@/lib/types";

import { AuditBadge } from "./AuditBadge";
import { MIN_REASON } from "./ReasonDialog";

export const REVEAL_SECONDS = 60;

export function RevealEmail({ userId, masked, ticketNumber }: { userId: number; masked: string | null; ticketNumber?: string }) {
  const allowed = useCan("users.reveal_email");
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [ticket, setTicket] = useState(ticketNumber ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState<{ email: string; until: number } | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!shown) return;
    const timer = setInterval(() => {
      const t = Date.now();
      setNow(t);
      if (t >= shown.until) setShown(null);
    }, 1000);
    return () => clearInterval(timer);
  }, [shown]);

  if (!masked) return <span className="text-muted-foreground">No email (child profile)</span>;

  const secondsLeft = shown ? Math.max(0, Math.ceil((shown.until - now) / 1000)) : 0;
  const ticketId = ticket.trim() ? ticketIdFromNumber(ticket) : null;
  const ticketOk = !ticket.trim() || ticketId !== null;
  const ok = reason.trim().length >= MIN_REASON && ticketOk;

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span className="font-medium" data-testid="email">
        {shown ? shown.email : masked}
      </span>
      {shown ? (
        <>
          <span className="text-[12px] text-muted-foreground" aria-live="polite">
            Hides in {secondsLeft} s
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={() => {
              void navigator.clipboard?.writeText(shown.email).then(
                () => toast("Copied"),
                () => toast("Couldn't copy"),
              );
            }}
          >
            <Copy /> Copy
          </Button>
          <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setShown(null)}>
            <EyeOff /> Hide
          </Button>
        </>
      ) : allowed ? (
        <Button variant="outline" size="sm" className="h-7 px-2" onClick={() => setOpen(true)}>
          <Eye /> Reveal
        </Button>
      ) : null}
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
        <DialogContent className="sm:max-w-md">
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!ok || busy) return;
              setBusy(true);
              setError(null);
              try {
                const result = await api.post<RevealedEmail>(`/users/${userId}/reveal-email`, {
                  reason: reason.trim(),
                  ticket_id: ticketId ?? undefined,
                });
                if (result.email) {
                  setNow(Date.now());
                  setShown({ email: result.email, until: Date.now() + REVEAL_SECONDS * 1000 });
                }
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
              <DialogTitle>Reveal this email address</DialogTitle>
              <DialogDescription>
                It shows for {REVEAL_SECONDS} seconds, then is masked again. Your name, the reason and the time are written to the audit log.
              </DialogDescription>
            </DialogHeader>
            <div className="mt-4 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="reveal-reason">Reason</Label>
                <Textarea
                  id="reveal-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="For example: replying by email to their ticket"
                  rows={3}
                  maxLength={500}
                  autoFocus
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="reveal-ticket">Ticket (optional)</Label>
                <Input id="reveal-ticket" value={ticket} onChange={(e) => setTicket(e.target.value)} placeholder="AN-0042" className="w-40" />
                {!ticketOk ? <p className="text-[12px] text-destructive">A ticket number looks like AN-0042.</p> : null}
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
                <Button type="submit" disabled={!ok || busy}>
                  {busy ? "Revealing…" : "Reveal"}
                </Button>
              </div>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </span>
  );
}
