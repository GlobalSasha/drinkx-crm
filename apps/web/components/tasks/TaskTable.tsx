"use client";

import { useRouter } from "next/navigation";
import { Check, ArrowUpRight, ListChecks } from "lucide-react";
import { C } from "@/lib/design-system";
import { type TaskRow, formatDueDateTime, isOverdue } from "@/lib/tasks";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/Empty";
import { Badge } from "@/components/ui/Badge";

interface Props {
  rows: TaskRow[];
  onComplete: (row: TaskRow) => void;
  isCompleting?: boolean;
  emptyText?: string;
}

// «Тип» column. Tasks are all manager-entered (no follow-up / no AI),
// so the badge only distinguishes overdue vs a normal task.
function TypeBadge({ row }: { row: TaskRow }) {
  if (isOverdue(row)) {
    return <Badge variant="rose">просрочено</Badge>;
  }
  return <Badge variant="success">задача</Badge>;
}

export function TaskTable({ rows, onComplete, isCompleting, emptyText }: Props) {
  const router = useRouter();

  if (rows.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon"><ListChecks /></EmptyMedia>
          <EmptyTitle>{emptyText ?? "Задач нет"}</EmptyTitle>
          <EmptyDescription>
            Когда менеджер поставит задачу — она появится в этом списке.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full border-collapse">
        <thead>
          <tr className="text-left">
            <th className="w-9 px-1 py-2" />
            <th className="px-2 py-2 type-table-header text-brand-muted">Задача</th>
            <th className="px-2 py-2 type-table-header text-brand-muted">Клиент</th>
            <th className="px-2 py-2 type-table-header text-brand-muted">Срок</th>
            <th className="px-2 py-2 type-table-header text-brand-muted">Тип</th>
            <th className="w-9 px-1 py-2" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const overdue = isOverdue(row);
            return (
              <tr
                key={row.id}
                role="link"
                tabIndex={0}
                aria-label={`Открыть лид: ${row.company ?? row.name}`}
                onClick={() => router.push(`/leads/${row.leadId}?tab=tasks`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    router.push(`/leads/${row.leadId}?tab=tasks`);
                  }
                }}
                className="group border-t border-brand-border cursor-pointer hover:bg-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-inset"
              >
                {/* Checkbox */}
                <td className="px-1 py-2.5 align-top">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!row.done && !isCompleting) onComplete(row);
                    }}
                    disabled={row.done || isCompleting}
                    aria-label={row.done ? "Выполнено" : "Отметить выполненной"}
                    className={`shrink-0 w-5 h-5 rounded-full border-[1.5px] flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
                      row.done
                        ? "border-success bg-success cursor-default"
                        : "border-brand-border hover:border-brand-accent hover:bg-brand-soft/40"
                    } disabled:opacity-60`}
                  >
                    {row.done && <Check size={12} className="text-white" />}
                  </button>
                </td>

                {/* Задача */}
                <td className="px-2 py-2.5 align-top">
                  <span
                    className={`type-body ${
                      row.done
                        ? "line-through text-brand-muted"
                        : "text-brand-primary"
                    }`}
                  >
                    {row.name}
                  </span>
                </td>

                {/* Клиент */}
                <td className="px-2 py-2.5 align-top">
                  <span className="type-caption text-brand-muted-strong">
                    {row.company ?? "—"}
                  </span>
                </td>

                {/* Срок */}
                <td className="px-2 py-2.5 align-top whitespace-nowrap">
                  <span
                    className={`type-caption ${
                      overdue ? "text-rose font-semibold" : "text-brand-muted"
                    }`}
                  >
                    {formatDueDateTime(row.due)}
                    {overdue && " · просрочено"}
                  </span>
                </td>

                {/* Тип */}
                <td className="px-2 py-2.5 align-top">
                  <TypeBadge row={row} />
                </td>

                {/* Action */}
                <td className="px-1 py-2.5 align-top text-right">
                  <ArrowUpRight
                    size={15}
                    className="text-brand-muted opacity-0 coarse:opacity-100 group-hover:opacity-100 transition-opacity inline-block"
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
