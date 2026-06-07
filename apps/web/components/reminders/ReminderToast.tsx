"use client";

import { Clock, X } from "lucide-react";
import type { MyTaskOut } from "@/lib/types";

interface Props {
  task: MyTaskOut;
  onOpen: () => void;
  onSnooze: () => void;
  onClose: () => void;
}

function dueTimeLabel(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

export function ReminderToast({ task, onOpen, onSnooze, onClose }: Props) {
  const time = dueTimeLabel(task.task_due_at);

  return (
    <div
      role="alert"
      className="pointer-events-auto w-[330px] max-w-full rounded-card border border-white/50 bg-white/75 backdrop-blur-2xl shadow-[0_8px_32px_rgba(0,0,0,0.18)] p-4 animate-[fadeInUp_0.28s_ease-out]"
    >
      <div className="flex items-start gap-2.5">
        <span className="shrink-0 w-7 h-7 rounded-full bg-warning/15 flex items-center justify-center mt-0.5">
          <Clock size={15} className="text-warning" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="type-caption font-mono uppercase tracking-wide text-brand-muted">
              Напоминание
            </span>
            <button
              type="button"
              onClick={onClose}
              aria-label="Закрыть напоминание"
              className="-mt-1 -mr-1 p-1 rounded-full text-brand-muted hover:text-brand-primary hover:bg-black/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              <X size={14} />
            </button>
          </div>
          <p className="type-body font-semibold text-brand-primary mt-0.5 line-clamp-2">
            {task.text}
          </p>
          <p className="type-caption text-brand-muted mt-0.5 truncate">
            {task.lead_company_name ? `${task.lead_company_name} · ` : ""}
            срок наступил{time ? ` · ${time}` : ""}
          </p>
          <div className="flex items-center gap-2 mt-3">
            <button
              type="button"
              onClick={onOpen}
              className="inline-flex items-center justify-center px-3.5 py-1.5 rounded-full type-caption font-semibold bg-brand-accent text-white hover:bg-brand-accent/90 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            >
              Открыть
            </button>
            <button
              type="button"
              onClick={onSnooze}
              className="inline-flex items-center justify-center px-3 py-1.5 rounded-full type-caption font-semibold text-brand-muted hover:text-brand-primary hover:bg-black/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              Отложить 10 мин
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
