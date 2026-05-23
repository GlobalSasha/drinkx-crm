"use client";

import * as React from "react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowData,
} from "@tanstack/react-table";
import { cn } from "@/lib/cn";

/**
 * DataTable — thin TanStack-react-table wrapper styled in brand tokens.
 *
 *   <DataTable
 *     columns={columns}
 *     data={rows}
 *     onRowClick={(row) => router.push(...)}
 *     emptyState={<Empty>…</Empty>}
 *   />
 *
 * Headless under the hood — TanStack handles row-model, future sorting,
 * pagination, column visibility. This first cut only wires the basics so
 * the migrated TaskTable behaves visually like prod; subsequent PRs can
 * layer on sort/select/paginate without changing the API.
 */

declare module "@tanstack/react-table" {
  // Allow per-column meta so callers can hint alignment without forking the type.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    align?: "left" | "right" | "center";
    width?: string;
    headerClassName?: string;
    cellClassName?: string;
  }
}

export interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  onRowClick?: (row: TData, event: React.MouseEvent | React.KeyboardEvent) => void;
  rowLabel?: (row: TData) => string;
  rowKey?: (row: TData) => string;
  emptyState?: React.ReactNode;
  className?: string;
}

export function DataTable<TData>({
  columns,
  data,
  onRowClick,
  rowLabel,
  rowKey,
  emptyState,
  className,
}: DataTableProps<TData>) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (data.length === 0 && emptyState !== undefined) {
    return <>{emptyState}</>;
  }

  return (
    <div className={cn("overflow-x-auto -mx-1", className)}>
      <table className="w-full border-collapse">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="text-left">
              {hg.headers.map((h) => {
                const meta = (h.column.columnDef.meta ?? {}) as {
                  headerClassName?: string;
                  width?: string;
                  align?: string;
                };
                return (
                  <th
                    key={h.id}
                    className={cn(
                      "px-2 py-2 type-table-header text-brand-muted",
                      meta.align === "right" && "text-right",
                      meta.align === "center" && "text-center",
                      meta.headerClassName,
                    )}
                    style={meta.width ? { width: meta.width } : undefined}
                  >
                    {h.isPlaceholder
                      ? null
                      : flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => {
            const rowData = row.original;
            const interactive = !!onRowClick;
            return (
              <tr
                key={rowKey ? rowKey(rowData) : row.id}
                role={interactive ? "link" : undefined}
                tabIndex={interactive ? 0 : undefined}
                aria-label={
                  interactive && rowLabel ? rowLabel(rowData) : undefined
                }
                onClick={
                  interactive ? (e) => onRowClick!(rowData, e) : undefined
                }
                onKeyDown={
                  interactive
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onRowClick!(rowData, e);
                        }
                      }
                    : undefined
                }
                className={cn(
                  "group border-t border-brand-border",
                  interactive &&
                    "cursor-pointer hover:bg-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-inset",
                )}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = (cell.column.columnDef.meta ?? {}) as {
                    cellClassName?: string;
                    align?: string;
                  };
                  return (
                    <td
                      key={cell.id}
                      className={cn(
                        "px-2 py-2.5 align-top",
                        meta.align === "right" && "text-right",
                        meta.align === "center" && "text-center",
                        meta.cellClassName,
                      )}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export type { ColumnDef };
