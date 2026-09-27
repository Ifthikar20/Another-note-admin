/** Loading, empty and error states: every page has all three (section 6.4). */
import type { UseQueryResult } from "@tanstack/react-query";
import { AlertTriangle, Inbox, Lock, RotateCw } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

export function EmptyState({ title, children, className }: { title: string; children?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-10 text-center", className)}>
      <Inbox className="size-5 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium">{title}</p>
      {children ? <div className="max-w-md text-[13px] text-muted-foreground">{children}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  const forbidden = error instanceof ApiError && error.status === 403;
  const Icon = forbidden ? Lock : AlertTriangle;
  return (
    <div role="alert" className={cn("flex flex-col items-center justify-center gap-2 px-6 py-10 text-center", className)}>
      <Icon className={cn("size-5", forbidden ? "text-muted-foreground" : "text-destructive")} aria-hidden />
      <p className="text-sm font-medium">{forbidden ? "Your role can't see this" : "This didn't load"}</p>
      <p className="max-w-md text-[13px] text-muted-foreground">{errorMessage(error)}</p>
      {onRetry && !forbidden ? (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-1">
          <RotateCw /> Try again
        </Button>
      ) : null}
    </div>
  );
}

export function LoadingBlock({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2 py-2", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-7 w-full" style={{ opacity: 1 - i * 0.12 }} />
      ))}
    </div>
  );
}

/**
 * The three states of one query, then the content. A refetch keeps the previous render
 * (at reduced opacity) rather than flashing back to a skeleton.
 */
export function QueryView<T>({
  query,
  children,
  isEmpty,
  empty,
  loading,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  loading?: ReactNode;
}) {
  if (query.isPending) return <>{loading ?? <LoadingBlock />}</>;
  if (query.isError && !query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const data = query.data as T;
  if (isEmpty?.(data)) return <>{empty ?? <EmptyState title="Nothing here yet" />}</>;
  return (
    <div className={cn("transition-opacity", query.isFetching && query.isPlaceholderData ? "opacity-60" : "opacity-100")}>
      {children(data)}
    </div>
  );
}
