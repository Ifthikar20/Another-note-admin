import { ScrollText } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** Marks an action that is written to the audit log, with who did it and why. */
export function AuditBadge({ text = "Recorded in the audit log with your name and reason." }: { text?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
          <ScrollText className="size-3" aria-hidden /> Audited
        </span>
      </TooltipTrigger>
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  );
}
