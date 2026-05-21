"use client";

import { useState } from "react";
import { Pencil, Trash2, Loader2, Check, X } from "lucide-react";
import {
  useNotes,
  useCreateNote,
  useUpdateNote,
  useDeleteNote,
} from "@/lib/hooks/use-notes";
import { useMe } from "@/lib/hooks/use-me";
import { C } from "@/lib/design-system";
import type { NoteOut } from "@/lib/types";

interface Props {
  leadId: string;
}

function formatAuthorDate(note: NoteOut): string {
  const d = new Date(note.created_at);
  const date = d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  const time = d.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${note.author_name} · ${date} ${time}`;
}

// Free-form client notes. Not tasks (no due/checkbox), not activities
// (never in the feed). Edit/delete restricted to author or admin.
export function NotesTab({ leadId }: Props) {
  const { data: notes, isLoading, isError } = useNotes(leadId);
  const me = useMe().data;
  const createNote = useCreateNote(leadId);
  const updateNote = useUpdateNote(leadId);
  const deleteNote = useDeleteNote(leadId);

  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  function canManage(note: NoteOut): boolean {
    if (!me) return false;
    return note.author_id === me.id || me.role === "admin";
  }

  function handleCreate() {
    const t = draft.trim();
    if (!t || createNote.isPending) return;
    createNote.mutate(t, { onSuccess: () => setDraft("") });
  }

  function startEdit(note: NoteOut) {
    setEditingId(note.id);
    setEditText(note.text);
  }

  function saveEdit() {
    const t = editText.trim();
    if (!t || !editingId || updateNote.isPending) return;
    updateNote.mutate(
      { noteId: editingId, text: t },
      { onSuccess: () => setEditingId(null) },
    );
  }

  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 sm:p-6">
      <h2 className="type-card-title text-brand-primary mb-4">Заметки</h2>

      {/* New note */}
      <div className="mb-5">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Написать заметку…"
          rows={3}
          maxLength={2000}
          className={`w-full bg-white border border-brand-border rounded-2xl px-4 py-2.5 text-sm text-brand-primary outline-none focus:border-brand-accent transition-colors resize-y`}
        />
        <div className="flex justify-end mt-2">
          <button
            type="button"
            onClick={handleCreate}
            disabled={!draft.trim() || createNote.isPending}
            className={`${C.button.primary} type-body px-4 py-2 disabled:opacity-40`}
          >
            {createNote.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              "Сохранить"
            )}
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 py-6 justify-center text-brand-muted">
          <Loader2 size={16} className="animate-spin" />
          <span className="type-caption">Загрузка…</span>
        </div>
      )}

      {!isLoading && isError && (
        <p className="type-caption text-rose py-4">Не удалось загрузить заметки</p>
      )}

      {!isLoading && !isError && (notes?.length ?? 0) === 0 && (
        <p className={`type-body ${C.color.mutedLight} py-6 text-center`}>
          Заметок пока нет. Добавьте наблюдение о клиенте.
        </p>
      )}

      {!isLoading && !isError && (notes?.length ?? 0) > 0 && (
        <ul className="flex flex-col gap-3">
          {notes!.map((note) => {
            const editing = editingId === note.id;
            const confirming = confirmDeleteId === note.id;
            return (
              <li
                key={note.id}
                className="rounded-2xl border border-brand-border p-4"
              >
                {editing ? (
                  <div>
                    <textarea
                      autoFocus
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      rows={3}
                      maxLength={2000}
                      className="w-full bg-white border border-brand-border rounded-2xl px-4 py-2.5 text-sm text-brand-primary outline-none focus:border-brand-accent resize-y"
                    />
                    <div className="flex gap-2 justify-end mt-2">
                      <button
                        type="button"
                        onClick={saveEdit}
                        disabled={!editText.trim() || updateNote.isPending}
                        className={`${C.button.primary} type-body px-3 py-1.5 disabled:opacity-40`}
                      >
                        <Check size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingId(null)}
                        aria-label="Отменить"
                        className={`${C.button.ghost} type-body px-3 py-1.5`}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="type-body text-brand-primary whitespace-pre-wrap break-words">
                      {note.text}
                    </p>
                    <div className="flex items-center justify-between gap-2 mt-2">
                      <span className="type-caption text-brand-muted">
                        {formatAuthorDate(note)}
                      </span>
                      {canManage(note) && (
                        <div className="flex items-center gap-1 shrink-0">
                          {confirming ? (
                            <span className="inline-flex items-center gap-2">
                              <span className="type-caption text-brand-muted">
                                Удалить?
                              </span>
                              <button
                                type="button"
                                onClick={() => {
                                  deleteNote.mutate(note.id);
                                  setConfirmDeleteId(null);
                                }}
                                className="type-caption font-semibold text-rose"
                              >
                                Да
                              </button>
                              <button
                                type="button"
                                onClick={() => setConfirmDeleteId(null)}
                                className="type-caption font-semibold text-brand-muted"
                              >
                                Нет
                              </button>
                            </span>
                          ) : (
                            <>
                              <button
                                type="button"
                                onClick={() => startEdit(note)}
                                aria-label="Редактировать"
                                className="p-1.5 rounded-full text-brand-muted hover:text-brand-accent hover:bg-brand-panel transition-colors"
                              >
                                <Pencil size={13} />
                              </button>
                              <button
                                type="button"
                                onClick={() => setConfirmDeleteId(note.id)}
                                aria-label="Удалить"
                                className="p-1.5 rounded-full text-brand-muted hover:text-rose hover:bg-rose/10 transition-colors"
                              >
                                <Trash2 size={13} />
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
