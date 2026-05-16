"use client";

import { useMemo } from "react";
import { ArrowDown, Calendar, ListTodo } from "lucide-react";
import type { FeedItemOut } from "@/lib/types";
import { formatDateShort } from "./_time";

interface Props {
  items: FeedItemOut[];
}

/**
 * Read-only pinned card at the top of the Activity feed. Surfaces
 * the EARLIEST open task (ascending due_at, NULLS last) so the
 * manager always sees the next thing to do without scrolling.
 *
 * The card is intentionally not editable — task edits happen in
 * the feed composer below. Clicking the card scrolls to the row
 * in the feed (anchor via #activity-{id}).
 *
 * Empty state: «Нет задач. Создайте задачу ↓» — points the user
 * at the composer.
 */
export function NextStepBanner({ items }: Props) {
  const nextTask = useMemo(() => {
    const open = items.filter((it) => it.type === "task" && !it.task_done);
    if (open.length === 0) return null;
    return open.slice().sort(byDueAsc)[0];
  }, [items]);

  if (!nextTask) {
    return (
      <div className="rounded-2xl border border-dashed border-brand-border px-4 py-3 flex items-center gap-2">
        <ListTodo size={13} className="text-brand-muted" />
        <p className="type-caption text-brand-muted">
          Нет задач. Создайте задачу
        </p>
        <ArrowDown size={11} className="text-brand-muted" />
      </div>
    );
  }

  const title =
    (nextTask.payload_json?.title as string | undefined) ||
    nextTask.body ||
    "Задача";

  return (
    <a
      href={`#activity-${nextTask.id}`}
      className="block rounded-2xl border border-brand-accent/30 bg-brand-soft/40 px-4 py-3 hover:bg-brand-soft/60 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2"
    >
      <p className="type-caption font-semibold uppercase tracking-wide text-brand-accent-text mb-1">
        Следующий шаг
      </p>
      <div className="flex items-center gap-2 flex-wrap">
        <ListTodo size={13} className="text-brand-primary shrink-0" />
        <span className="type-body font-semibold text-brand-primary truncate">
          {title}
        </span>
        {nextTask.task_due_at && (
          <span className="inline-flex items-center gap-1 type-caption text-brand-muted">
            <Calendar size={11} />
            до {formatDateShort(nextTask.task_due_at)}
          </span>
        )}
      </div>
    </a>
  );
}

function byDueAsc(a: FeedItemOut, b: FeedItemOut): number {
  // NULL due dates sort to the end so dated tasks always win.
  if (!a.task_due_at && !b.task_due_at) return 0;
  if (!a.task_due_at) return 1;
  if (!b.task_due_at) return -1;
  return new Date(a.task_due_at).getTime() - new Date(b.task_due_at).getTime();
}
