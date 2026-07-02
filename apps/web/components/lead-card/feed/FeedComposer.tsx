"use client";

import { useEffect, useRef, useState } from "react";
import {
  Calendar,
  ListTodo,
  Loader2,
  MessageSquare,
  Paperclip,
  Phone,
  Send,
  X,
} from "lucide-react";
import { useCreateActivity } from "@/lib/hooks/use-feed";
import { useUploadLeadFile } from "@/lib/hooks/use-task-files";

interface Props {
  leadId: string;
  /** Seed value pushed in by callers — prefills the comment box. */
  seed?: string;
  onSeedConsumed?: () => void;
  /** Lead Card v3 — switch the composer into a specific mode and
   *  focus the input. Used by `NextStepBanner` to drop the user
   *  straight into task creation. Cleared via `onModeRequestConsumed`
   *  after applying. */
  modeRequest?: Mode | null;
  onModeRequestConsumed?: () => void;
}

type Mode = "comment" | "task" | "call" | "file";

/**
 * Activity composer with 4 modes (Комментарий / Задача / Звонок / Файл).
 * Default mode is `comment`; the mode switcher buttons live to the right
 * of the input.
 */
export function FeedComposer({
  leadId,
  seed,
  onSeedConsumed,
  modeRequest,
  onModeRequestConsumed,
}: Props) {
  const [mode, setMode] = useState<Mode>("comment");
  const [text, setText] = useState("");
  const [taskDue, setTaskDue] = useState<string>(""); // datetime-local: yyyy-mm-ddTHH:mm
  const [callMinutes, setCallMinutes] = useState<string>("");
  const [picked, setPicked] = useState<File | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const create = useCreateActivity(leadId);
  const uploadFile = useUploadLeadFile(leadId);
  const isPending = create.isPending || uploadFile.isPending;

  // External seed — prefill the comment box and focus it.
  useEffect(() => {
    if (seed === undefined) return;
    setText(seed);
    setMode("comment");
    setTimeout(() => inputRef.current?.focus(), 30);
    onSeedConsumed?.();
  }, [seed, onSeedConsumed]);

  // External mode-switch (e.g. NextStepBanner empty-state strip).
  useEffect(() => {
    if (!modeRequest) return;
    setMode(modeRequest);
    setTimeout(() => inputRef.current?.focus(), 30);
    onModeRequestConsumed?.();
  }, [modeRequest, onModeRequestConsumed]);

  function reset() {
    setText("");
    setTaskDue("");
    setCallMinutes("");
    setPicked(null);
  }

  async function handleSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const value = text.trim();
    // File mode: a file must be picked; caption is optional (no text guard)
    if (mode !== "file" && !value) return;

    if (mode === "comment") {
      try {
        await create.mutateAsync({ type: "comment", body: value });
        reset();
      } catch {
        /* keep text */
      }
      return;
    }

    if (mode === "task") {
      if (!taskDue) return;
      const due = new Date(taskDue); // datetime-local — exact time the manager set
      if (Number.isNaN(due.getTime())) return;
      try {
        await create.mutateAsync({
          type: "task",
          body: value,
          task_due_at: due.toISOString(),
          payload_json: { title: value, source: "feed_composer" },
        });
        reset();
      } catch {
        /* keep text */
      }
      return;
    }

    if (mode === "call") {
      const minutes = Number(callMinutes);
      try {
        await create.mutateAsync({
          type: "phone",
          body: value,
          payload_json: {
            duration_minutes: Number.isFinite(minutes) && minutes > 0 ? minutes : null,
            source: "feed_composer",
          },
        });
        reset();
      } catch {
        /* keep text */
      }
      return;
    }

    if (mode === "file") {
      if (!picked) return;
      try {
        await uploadFile.mutateAsync({
          file: picked,
          caption: value || undefined,
        });
        reset();
      } catch {
        /* error surfaced via mutation state; keep state in place */
      }
      return;
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && mode === "comment") {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-card border border-brand-border bg-white p-2.5"
    >
      <div className="flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            mode === "comment"
              ? "Написать комментарий…"
              : mode === "task"
                ? "Название задачи..."
                : mode === "call"
                  ? "Заметка по звонку..."
                  : "Подпись к файлу (необязательно)"
          }
          rows={mode === "comment" ? 1 : 2}
          className="flex-1 min-w-0 resize-none bg-transparent outline-none type-body text-brand-primary placeholder:text-brand-muted px-2 py-1.5"
        />
        <div className="flex items-center gap-1 shrink-0">
          <ModeButton
            active={mode === "comment"}
            onClick={() => setMode("comment")}
            label="Комментарий"
            icon={<MessageSquare size={14} />}
          />
          <ModeButton
            active={mode === "task"}
            onClick={() => setMode("task")}
            label="Задача"
            icon={<ListTodo size={14} />}
          />
          <ModeButton
            active={mode === "call"}
            onClick={() => setMode("call")}
            label="Звонок"
            icon={<Phone size={14} />}
          />
          <ModeButton
            active={mode === "file"}
            onClick={() => setMode("file")}
            label="Файл"
            icon={<Paperclip size={14} />}
          />
        </div>
      </div>

      {/* Per-mode extra controls */}
      {mode === "task" && (
        <div className="flex items-center gap-2 mt-2 px-2">
          <label className="inline-flex items-center gap-1.5 type-caption text-brand-muted">
            <Calendar size={12} />
            <input
              type="datetime-local"
              value={taskDue}
              onChange={(e) => setTaskDue(e.target.value)}
              aria-label="Срок и время задачи"
              className="bg-transparent outline-none type-caption text-brand-primary"
            />
          </label>
          <button
            type="submit"
            disabled={isPending || !text.trim() || !taskDue}
            className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 type-caption font-semibold bg-brand-accent text-white rounded-full hover:bg-brand-accent/90 disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
          >
            {isPending && <Loader2 size={12} className="animate-spin" />}
            Создать задачу
          </button>
        </div>
      )}

      {mode === "call" && (
        <div className="flex items-center gap-2 mt-2 px-2">
          <label className="inline-flex items-center gap-1.5 type-caption text-brand-muted">
            Длительность
            <input
              type="number"
              min={0}
              value={callMinutes}
              onChange={(e) => setCallMinutes(e.target.value)}
              placeholder="мин"
              className="w-16 bg-transparent outline-none type-caption text-brand-primary"
            />
          </label>
          <button
            type="submit"
            disabled={isPending || !text.trim()}
            className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 type-caption font-semibold bg-brand-accent text-white rounded-full hover:bg-brand-accent/90 disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
          >
            {isPending && <Loader2 size={12} className="animate-spin" />}
            Записать звонок
          </button>
        </div>
      )}

      {mode === "file" && (
        <div className="flex items-center gap-2 mt-2 px-2">
          {!picked ? (
            <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full type-caption font-semibold cursor-pointer bg-brand-bg border border-brand-border hover:border-brand-accent transition-colors w-fit">
              <Paperclip size={13} /> Выбрать файл
              <input
                type="file"
                className="hidden"
                accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.rtf,.png,.jpg,.jpeg,.gif,.webp,.heic,.mp3,.wav,.m4a,.ogg"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) setPicked(f);
                  e.target.value = "";
                }}
              />
            </label>
          ) : (
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full type-caption bg-brand-bg w-fit">
              <Paperclip size={12} className="text-brand-muted" />
              <span className="text-brand-primary">{picked.name}</span>
              <button
                type="button"
                onClick={() => setPicked(null)}
                aria-label="Отменить выбор"
                className="text-brand-muted hover:text-rose"
              >
                <X size={12} />
              </button>
            </div>
          )}
          <button
            type="submit"
            disabled={isPending || !picked}
            className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 type-caption font-semibold bg-brand-accent text-white rounded-full hover:bg-brand-accent/90 disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
          >
            {isPending && <Loader2 size={12} className="animate-spin" />}
            Загрузить
          </button>
        </div>
      )}

      {mode === "comment" && (
        <div className="flex items-center justify-end mt-1 px-2">
          <button
            type="submit"
            disabled={isPending || !text.trim()}
            aria-label="Отправить"
            className="inline-flex items-center gap-1 px-3 py-1 type-caption font-semibold bg-brand-accent text-white rounded-full hover:bg-brand-accent/90 disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
          >
            {isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Send size={12} />
            )}
            Отправить
          </button>
        </div>
      )}
    </form>
  );
}

function ModeButton({
  active,
  onClick,
  label,
  icon,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={`inline-flex items-center justify-center w-8 h-8 coarse:w-10 coarse:h-10 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
        active
          ? "bg-brand-accent text-white"
          : "text-brand-muted hover:text-brand-primary hover:bg-brand-bg"
      }`}
    >
      {icon}
    </button>
  );
}
