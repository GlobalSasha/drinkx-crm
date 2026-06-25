"use client";

import { useState } from "react";
import { Pin, Plus, X, Loader2 } from "lucide-react";
import { C } from "@/lib/design-system";
import {
  useReminders,
  useCreateReminder,
  useUpdateReminder,
  useDeleteReminder,
} from "@/lib/hooks/use-reminders";

// Personal sticky-notes block for the Today screen. No lead, no due date.
export function RemindersWidget() {
  const { data: reminders = [], isLoading } = useReminders();
  const create = useCreateReminder();
  const update = useUpdateReminder();
  const remove = useDeleteReminder();

  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  function handleAdd() {
    const t = text.trim();
    if (!t || create.isPending) return;
    create.mutate(t, {
      onSuccess: () => {
        setText("");
        setAdding(false);
      },
    });
  }

  function startEdit(id: string, current: string) {
    setEditingId(id);
    setEditText(current);
  }

  function commitEdit() {
    if (!editingId || update.isPending) return;
    const t = editText.trim();
    const orig = reminders.find((r) => r.id === editingId);
    if (!t || (orig && t === orig.text)) {
      setEditingId(null);
      return;
    }
    update.mutate(
      { id: editingId, text: t },
      { onSuccess: () => setEditingId(null) },
    );
  }

  return (
    <div className="bg-white border border-brand-border rounded-card p-5 h-full flex flex-col">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Pin size={16} className="text-brand-muted" />
          <h3 className={`type-caption font-bold italic ${C.color.text}`}>
            Напоминания
          </h3>
        </div>
        {!adding && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            aria-label="Добавить напоминание"
            className="w-6 h-6 rounded-full bg-brand-panel flex items-center justify-center text-brand-muted hover:text-brand-accent transition-colors"
          >
            <Plus size={13} />
          </button>
        )}
      </div>

      <div className="flex flex-col gap-1.5 mt-5 flex-1">
        {/* Inline add */}
        {adding && (
          <div className="flex gap-2 items-center mb-1">
            <input
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAdd();
                if (e.key === "Escape") {
                  setAdding(false);
                  setText("");
                }
              }}
              maxLength={500}
              placeholder="Напоминание…"
              disabled={create.isPending}
              className={`flex-1 ${C.form.field} py-2 text-sm`}
            />
            <button
              type="button"
              onClick={handleAdd}
              disabled={!text.trim() || create.isPending}
              aria-label="Сохранить"
              className={`${C.button.primary} type-body px-3 py-2 disabled:opacity-40`}
            >
              {create.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Plus size={14} />
              )}
            </button>
            <button
              type="button"
              onClick={() => {
                setAdding(false);
                setText("");
              }}
              aria-label="Отменить"
              className={`${C.button.ghost} type-body px-3 py-2`}
            >
              <X size={14} />
            </button>
          </div>
        )}

        {isLoading && (
          <p className={`type-caption ${C.color.mutedLight}`}>Загрузка…</p>
        )}

        {!isLoading &&
          reminders.map((r) => {
            const isEditing = editingId === r.id;
            return (
              <div
                key={r.id}
                className="group flex items-start gap-2 px-3 py-2 rounded-card bg-brand-bg"
              >
                {isEditing ? (
                  <input
                    autoFocus
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onBlur={commitEdit}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitEdit();
                      if (e.key === "Escape") setEditingId(null);
                    }}
                    maxLength={500}
                    disabled={update.isPending}
                    className={`flex-1 bg-white border border-brand-accent/40 rounded-lg px-2 py-1 type-caption ${C.color.text} outline-none focus:border-brand-accent disabled:opacity-60`}
                  />
                ) : (
                  <button
                    type="button"
                    onClick={() => startEdit(r.id, r.text)}
                    title="Нажмите, чтобы редактировать"
                    className={`type-caption ${C.color.text} flex-1 break-words text-left cursor-text hover:text-brand-accent-text transition-colors`}
                  >
                    {r.text}
                  </button>
                )}
                {!isEditing && (
                  <button
                    type="button"
                    onClick={() => remove.mutate(r.id)}
                    aria-label="Удалить напоминание"
                    className="shrink-0 text-brand-muted hover:text-rose opacity-0 group-hover:opacity-100 transition"
                  >
                    <X size={13} />
                  </button>
                )}
              </div>
            );
          })}

        {!isLoading && reminders.length === 0 && !adding && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="w-full py-2 rounded-xl border border-dashed border-brand-border text-brand-muted type-caption flex items-center justify-center gap-1"
          >
            <Plus size={12} aria-hidden /> Добавить напоминание
          </button>
        )}
      </div>
    </div>
  );
}
