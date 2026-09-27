/** A time as "3 h ago", with the exact local time on hover (and for screen readers). */
import { formatDateTime, formatRelative, formatShortDateTime } from "@/lib/format";

import { cn } from "@/lib/utils";

export function RelativeTime({ iso, className, long }: { iso: string | null | undefined; className?: string; long?: boolean }) {
  if (!iso) return <span className={className}>—</span>;
  return (
    <time dateTime={iso} title={formatDateTime(iso)} className={cn("whitespace-nowrap", className)}>
      {formatRelative(iso, Date.now(), long ? "long" : "short")}
    </time>
  );
}

export function ExactTime({ iso, className }: { iso: string | null | undefined; className?: string }) {
  if (!iso) return <span className={className}>—</span>;
  return (
    <time dateTime={iso} title={formatDateTime(iso)} className={cn("whitespace-nowrap", className)}>
      {formatShortDateTime(iso)}
    </time>
  );
}
