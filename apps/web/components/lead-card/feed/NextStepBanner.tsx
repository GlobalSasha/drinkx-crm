"use client";

import { useMemo } from "react";
import { Calendar, ListTodo, Plus } from "lucide-react";
import type { FeedItemOut } from "@/lib/types";
import { formatDateShort } from "./_time";

interface Props {
  items: FeedItemOut[];
  /** Fires when the empty-state strip is clicked. Parent should
   *  focus the composer in task mode. */
  onCreateTaskRequest?: () => void;
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
export function NextStepBanner({ items, onCreateTaskRequest }: Props) {
  const nextTask = useMemo(() => {
    const open = items.filter((it) => it.type === "task" && !it.task_done);
    if (open.length === 0) return null;
    return open.slice().sort(byDueAsc)[0];
  }, [items]);

  if (!nextTask) {
    // Lead Card v2 — thin dashed strip instead of the big banner.
    // Click jumps straight into the composer in task mode.
    return (
      <button
        type="button"
        onClick={onCreateTaskRequest}
        className="w-full rounded-xl border border-dashed border-brand-border px-4 py-2.5 flex items-center justify-center gap-2 type-caption text-brand-muted hover:border-brand-accent hover:text-brand-accent-text transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2"
      >
        <Plus size={12} />
        Поставить задачу как следующий шаг
      </button>
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
