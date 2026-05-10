"use client";
import { useState } from "react";
import { Plus, Check, Trash2, Calendar, ClipboardList } from "lucide-react";
import {
  useFollowups,
  useCreateFollowup,
  useCompleteFollowup,
  useDeleteFollowup,
} from "@/lib/hooks/use-followups";

interface Props {
  leadId: string;
}

export function FollowupsRail({ leadId }: Props) {
  const { data: followups = [], isLoading } = useFollowups(leadId);
  const createFollowup = useCreateFollowup(leadId);
  const completeFollowup = useCompleteFollowup(leadId);
  const deleteFollowup = useDeleteFollowup(leadId);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [dueAt, setDueAt] = useState("");

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    createFollowup.mutate(
      { name: name.trim(), due_at: dueAt || null },
      {
        onSuccess: () => {
          setName("");
          setDueAt("");
          setShowForm(false);
        },
      }
    );
  }

  const pending = followups.filter((f) => f.status === "pending");
  const completed = followups.filter((f) => f.status === "completed");

  return (
    <div className="bg-white border border-black/5 rounded-2xl shadow-soft p-5 min-h-[120px]">
      <div className="flex items-center justify-between mb-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-2">
          Этапы работы
        </p>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="p-1 rounded-lg hover:bg-canvas text-muted hover:text-ink transition-colors"
        >
          <Plus size={14} />
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleAdd} className="mb-3 space-y-2">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Название..."
            autoFocus
            className="w-full px-3 py-2 text-xs bg-canvas border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-all"
          />
          <input
            type="datetime-local"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            className="w-full px-3 py-1.5 text-xs bg-canvas border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-all"
          />
          <div className="flex gap-1.5">
            <button
              type="submit"
              disabled={!name.trim() || createFollowup.isPending}
              className="flex-1 py-1.5 text-xs font-semibold bg-ink text-white rounded-pill hover:bg-ink/90 disabled:opacity-40 transition-all"
            >
              {createFollowup.isPending ? "..." : "Добавить"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="px-3 py-1.5 text-xs font-semibold text-muted bg-canvas rounded-pill hover:bg-canvas-2 transition-all"
            >
              ✕
            </button>
          </div>
        </form>
      )}

      {isLoading && (
        <p className="text-xs text-muted-2 text-center py-2">Загрузка...</p>
      )}

      <div className="space-y-1.5">
        {pending.map((fu) => (
          <div
            key={fu.id}
            className="flex items-start gap-2 group"
          >
            <button
              onClick={() => completeFollowup.mutate(fu.id)}
              className="mt-0.5 shrink-0 text-muted hover:text-success transition-colors"
            >
              <Check size={13} />
            </button>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-ink truncate">{fu.name}</p>
              {fu.due_at && (
                <div className="flex items-center gap-1 text-[10px] text-muted-2 mt-0.5">
                  <Calendar size={9} />
                  {new Date(fu.due_at).toLocaleDateString("ru-RU", {
                    day: "2-digit",
                    month: "short",
                  })}
                </div>
              )}
            </div>
            <button
              onClick={() => deleteFollowup.mutate(fu.id)}
              className="opacity-0 group-hover:opacity-100 shrink-0 text-muted hover:text-rose transition-all"
            >
              <Trash2 size={11} />
            </button>
          </div>
        ))}

        {pending.length === 0 && !showForm && (
          <div className="flex flex-col items-center gap-1.5 py-3 text-center">
            <ClipboardList size={16} className="text-muted-3" />
            <p className="text-[11px] font-semibold text-muted-2">Нет задач</p>
            <p className="text-[10px] text-muted-3">Нажмите + чтобы добавить</p>
          </div>
        )}
      </div>

      {/* Completed */}
      {completed.length > 0 && (
        <div className="mt-3 pt-3 border-t border-black/5">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-3 mb-1.5">
            Выполнено ({completed.length})
          </p>
          <div className="space-y-1">
            {completed.slice(0, 3).map((fu) => (
              <p key={fu.id} className="text-[10px] text-muted-2 line-through truncate">
                {fu.name}
              </p>
            ))}
            {completed.length > 3 && (
              <p className="text-[10px] text-muted-3">+{completed.length - 3} ещё</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
