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
} from "lucide-react";
import { useAskChak, useCreateActivity } from "@/lib/hooks/use-feed";

interface Props {
  leadId: string;
  /** Seed value pushed in by callers (e.g. «@Чак » from FeedItemAI button). */
  seed?: string;
  onSeedConsumed?: () => void;
  /** Lead Card v2 — switch the composer into a specific mode and
   *  focus the input. Used by `NextStepBanner` to drop the user
   *  straight into task creation. Cleared via `onModeRequestConsumed`
   *  after applying. */
  modeRequest?: Mode | null;
  onModeRequestConsumed?: () => void;
}

type Mode = "comment" | "task" | "call" | "file";

/**
 * Bottom-of-feed composer with 4 modes. Default mode is `comment`; the
 * mode switcher buttons live to the right of the input.
 *
 * «@Чак» (case-insensitive, at the start of the text) routes the
 * submission to the ask-chak endpoint instead of creating a regular
 * comment. The marker is stripped before the question is sent.
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
  const [taskDue, setTaskDue] = useState<string>(""); // yyyy-mm-dd
  const [callMinutes, setCallMinutes] = useState<string>("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const create = useCreateActivity(leadId);
  const ask = useAskChak(leadId);
  const isPending = create.isPending || ask.isPending;

  // External seed (e.g. «Спросить подробнее» button on an AI message)
  useEffect(() => {
    if (seed === undefined) return;
    setText(`@Чак ${seed}`.trim());
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
  }

  function isAskChak(value: string): { match: boolean; question: string } {
    // Match @Чак at start (with optional space), case-insensitive on the
    // word. Strip the marker so the question is just the user's text.
    const m = value.match(/^@?Чак\s*[:,—-]?\s*/i);
    if (m) return { match: true, question: value.slice(m[0].length).trim() };
    return { match: false, question: value };
  }

  async function handleSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const value = text.trim();
    if (!value) return;

    if (mode === "comment") {
      const { match, question } = isAskChak(value);
      if (match) {
        if (!question) return;
        try {
          await ask.mutateAsync(question);
          reset();
        } catch {
          /* error surfaced via mutation state; keep text in place */
        }
        return;
      }
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
      const due = new Date(taskDue);
      // Snap to end-of-day so a "до 20 мая" task isn't due at midnight.
      due.setHours(23, 59, 0, 0);
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
      // File upload flow is not wired in this sprint — the composer
      // still accepts a body so a manager can record a stub. Real
      // upload arrives with the dedicated file-upload endpoint.
      try {
        await create.mutateAsync({
          type: "file",
          body: value,
          payload_json: { source: "feed_composer", note: "upload_tbd" },
        });
        reset();
      } catch {
        /* keep text */
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
      className="rounded-2xl border border-brand-border bg-white p-2.5"
    >
      <div className="flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            mode === "comment"
              ? "Написать комментарий или @Чак..."
              : mode === "task"
                ? "Название задачи..."
                : mode === "call"
                  ? "Заметка по звонку..."
                  : "Описание файла..."
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
              type="date"
              value={taskDue}
              onChange={(e) => setTaskDue(e.target.value)}
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
          <span className="type-caption text-brand-muted">
            Загрузка файлов появится в следующем спринте — пока сохраняется только описание.
          </span>
          <button
            type="submit"
            disabled={isPending || !text.trim()}
            className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 type-caption font-semibold bg-brand-accent text-white rounded-full hover:bg-brand-accent/90 disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
          >
            {isPending && <Loader2 size={12} className="animate-spin" />}
            Сохранить
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
      className={`inline-flex items-center justify-center w-8 h-8 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
        active
          ? "bg-brand-accent text-white"
          : "text-brand-muted hover:text-brand-primary hover:bg-brand-bg"
      }`}
    >
      {icon}
    </button>
  );
}
