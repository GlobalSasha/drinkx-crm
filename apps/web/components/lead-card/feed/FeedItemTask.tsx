"use client";

import { CheckSquare, ListTodo, Paperclip, Square } from "lucide-react";
import type { FeedItemOut } from "@/lib/types";
import { useCompleteTask } from "@/lib/hooks/use-feed";
import { formatDateShort, formatTimeShort } from "./_time";

interface Props {
  item: FeedItemOut;
  leadId: string;
}

export function FeedItemTask({ item, leadId }: Props) {
  const complete = useCompleteTask(leadId);
  const author = item.author_name || "Менеджер";
  const done = item.task_done;
  const title = (item.payload_json?.title as string | undefined) ?? item.body ?? "Задача";

  return (
    <div className="flex gap-3 group">
      <div className="shrink-0 w-7 h-7 rounded-full bg-brand-panel flex items-center justify-center">
        <ListTodo size={13} className="text-brand-muted-strong" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <p className="type-caption text-brand-muted">
            <span className="font-semibold text-brand-primary">{author}</span>
            <span className="mx-1.5">·</span>
            <span>Задача</span>
            <span className="mx-1.5">·</span>
            <span>{formatTimeShort(item.created_at)}</span>
          </p>
          {item.task_due_at && (
            <span className="type-caption text-brand-muted ml-auto">
              📅 до {formatDateShort(item.task_due_at)}
            </span>
          )}
        </div>

        <div className="mt-1 rounded-2xl border border-brand-border bg-white p-3">
          <div className="flex items-start gap-2">
            <button
              type="button"
              onClick={() => !done && complete.mutate(item.id)}
              disabled={done || complete.isPending}
              aria-label={done ? "Задача выполнена" : "Отметить выполненной"}
              className="shrink-0 mt-0.5 text-brand-muted hover:text-brand-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            >
              {done ? (
                <CheckSquare size={16} className="text-success" />
              ) : (
                <Square size={16} />
              )}
            </button>
            <div className="flex-1 min-w-0">
              <p
                className={`type-body ${
                  done
                    ? "line-through text-brand-muted"
                    : "text-brand-primary"
                }`}
              >
                {title}
              </p>
              {item.file_url && (
                <a
                  href={item.file_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 mt-1 type-caption text-brand-accent-text hover:underline"
                >
                  <Paperclip size={11} />
                  {item.file_kind || "Файл"}
                </a>
              )}
            </div>
            {!done && (
              <button
                type="button"
                onClick={() => complete.mutate(item.id)}
                disabled={complete.isPending}
                className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1 type-caption font-semibold text-brand-accent-text bg-brand-soft hover:bg-brand-soft/80 rounded-full transition-colors disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
              >
                Выполнено
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
