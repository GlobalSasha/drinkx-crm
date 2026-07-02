"use client";

import { useState } from "react";
import { MessageSquare, Pencil, Check, X, Loader2 } from "lucide-react";
import type { FeedItemOut } from "@/lib/types";
import { useMe } from "@/lib/hooks/use-me";
import { useUpdateComment } from "@/lib/hooks/use-feed";
import { formatTimeShort } from "./_time";

interface Props {
  item: FeedItemOut;
}

// The backend sets payload_json.edited once a comment's text is changed
// (exact flag — no timestamp guessing).
function wasEdited(item: FeedItemOut): boolean {
  return item.payload_json?.edited === true;
}

export function FeedItemComment({ item }: Props) {
  const { data: me } = useMe();
  const update = useUpdateComment(item.lead_id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const author = item.author_name || "Менеджер";
  // ask-Blake questions are immutable (the backend rejects edits) — they're
  // half of an AI Q/A pair. Don't offer the affordance for them.
  const isAskBlake = item.payload_json?.source === "ask_blake";
  // Only the comment's author (or an admin) may edit — the backend
  // enforces the same rule; this just gates the affordance.
  const canEdit =
    !!me &&
    !!item.user_id &&
    !isAskBlake &&
    (item.user_id === me.id || me.role === "admin");

  function startEdit() {
    setDraft(item.body ?? "");
    setEditing(true);
  }

  async function save() {
    const next = draft.trim();
    if (!next || next === (item.body ?? "")) {
      setEditing(false);
      return;
    }
    try {
      await update.mutateAsync({ activityId: item.id, body: next });
      setEditing(false);
    } catch {
      /* keep the editor open on error so the manager can retry */
    }
  }

  return (
    <div className="flex gap-3 group">
      <div className="shrink-0 w-7 h-7 rounded-full bg-brand-panel flex items-center justify-center">
        <MessageSquare size={13} className="text-brand-muted-strong" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="type-caption text-brand-muted min-w-0 truncate">
            <span className="font-semibold text-brand-primary">{author}</span>
            <span className="mx-1.5">·</span>
            <span>{formatTimeShort(item.created_at)}</span>
            {wasEdited(item) && <span className="ml-1.5">· изменено</span>}
          </p>
          {canEdit && !editing && (
            <button
              type="button"
              onClick={startEdit}
              aria-label="Редактировать комментарий"
              className="ml-auto shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-full text-brand-muted opacity-0 coarse:opacity-100 group-hover:opacity-100 hover:text-brand-primary hover:bg-brand-panel transition-colors focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            >
              <Pencil size={13} />
            </button>
          )}
        </div>

        {editing ? (
          <div className="mt-1.5">
            <textarea
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.preventDefault();
                  setEditing(false);
                }
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  void save();
                }
              }}
              rows={3}
              maxLength={4000}
              disabled={update.isPending}
              className="w-full type-body bg-white border border-brand-accent/40 rounded-xl px-3 py-2 text-brand-primary outline-none focus:border-brand-accent resize-y disabled:opacity-60"
            />
            <div className="flex items-center justify-end gap-2 mt-2">
              <button
                type="button"
                onClick={() => setEditing(false)}
                disabled={update.isPending}
                aria-label="Отменить"
                className="inline-flex items-center justify-center w-8 h-8 rounded-full hover:bg-brand-panel text-brand-muted transition active:scale-[0.96] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
              >
                <X size={14} />
              </button>
              <button
                type="button"
                onClick={save}
                disabled={update.isPending || !draft.trim()}
                aria-label="Сохранить"
                className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-success/10 text-success hover:bg-success/20 transition active:scale-[0.96] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
              >
                {update.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Check size={14} />
                )}
              </button>
            </div>
          </div>
        ) : (
          item.body && (
            <p className="type-body text-brand-primary mt-1 whitespace-pre-wrap break-words">
              {item.body}
            </p>
          )
        )}
      </div>
    </div>
  );
}
