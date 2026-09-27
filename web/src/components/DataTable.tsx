/**
 * Dense tables: numbers right-aligned with tabular figures, rows that open something are
 * clickable and reachable with the keyboard, and a "Load more" footer for cursor paging.
 */
import { useEffect, useRef, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  numeric?: boolean;
  className?: string;
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  selectedIndex,
  rowClassName,
  label,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string | number;
  onRowClick?: (row: T, index: number) => void;
  selectedIndex?: number;
  rowClassName?: (row: T) => string | undefined;
  label: string;
}) {
  const selected = useRef<HTMLTableRowElement | null>(null);
  useEffect(() => {
    selected.current?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);
  return (
    <Table aria-label={label}>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          {columns.map((c) => (
            <TableHead key={c.key} className={cn("h-9 whitespace-nowrap px-3 text-[12px]", c.numeric && "text-right", c.className)}>
              {c.header}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, i) => {
          const isSelected = selectedIndex === i;
          return (
            <TableRow
              key={rowKey(row)}
              ref={isSelected ? selected : undefined}
              data-state={isSelected ? "selected" : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(row, i) : undefined}
              onKeyDown={
                onRowClick
                  ? (e) => {
                      if (e.key === "Enter" && e.target === e.currentTarget) onRowClick(row, i);
                    }
                  : undefined
              }
              className={cn(onRowClick && "cursor-pointer", isSelected && "bg-muted", rowClassName?.(row))}
            >
              {columns.map((c) => (
                <TableCell key={c.key} className={cn("px-3 py-2 text-[13px]", c.numeric && "num text-right", c.className)}>
                  {c.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export function LoadMore({ hasMore, loading, onClick, shown }: { hasMore: boolean; loading: boolean; onClick: () => void; shown: number }) {
  return (
    <div className="flex items-center justify-between border-t px-3 py-2 text-[12px] text-muted-foreground">
      <span className="num">{shown.toLocaleString("en-US")} shown</span>
      {hasMore ? (
        <Button variant="outline" size="sm" onClick={onClick} disabled={loading}>
          {loading ? "Loading…" : "Load more"}
        </Button>
      ) : (
        <span>That's everything</span>
      )}
    </div>
  );
}
