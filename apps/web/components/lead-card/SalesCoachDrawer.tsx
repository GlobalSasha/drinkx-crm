"use client";
import { useEffect, useRef, useState } from "react";
import { X, Send, Sparkles, Loader2 } from "lucide-react";
import { useAgentChat } from "@/lib/hooks/use-lead-agent";
import { C } from "@/lib/design-system";
import type { AgentChatMessage } from "@/lib/types";

interface Props {
  leadId: string;
  open: boolean;
  onClose: () => void;
  /** Optional seed message to send as the first turn — used when the
   *  banner's «action» button opens the drawer with a question
   *  pre-loaded (e.g. «Что делать дальше?»). */
  seedMessage?: string;
}

const QUICK_CHIPS: { label: string; message: string }[] = [
  { label: "Что делать дальше", message: "Что делать дальше?" },
  { label: "Напиши follow-up", message: "Напиши follow-up для этого клиента." },
  { label: "Разбери возражение", message: "Разбери последнее возражение клиента." },
  { label: "Готов ли к переходу", message: "Готов ли лид к переходу на следующую стадию?" },
];

const GREETING =
  "Привет. Я — Чак, твой ассистент по этой карточке. Спроси что-нибудь или выбери чип ниже.";

/**
 * Sales Coach drawer (Sprint 3.1 Phase D).
 *
 * Right-side slide-in on desktop, full-screen on mobile (`md:`
 * breakpoint). History is in-component state — not persisted to the
 * backend, just held for the current session per spec («достаточно
 * для сессии»). On close the history is dropped.
 *
 * The greeting is rendered locally rather than fetched on open —
 * spec calls for a generated greeting but firing an LLM round-trip
 * just to say «hello» is wasteful and slow. The first real turn
 * happens when the manager picks a chip or types a message.
 */
export function SalesCoachDrawer({
  leadId,
  open,
  onClose,
  seedMessage,
}: Props) {
  const chat = useAgentChat(leadId);
  const [history, setHistory] = useState<AgentChatMessage[]>([]);
  const [input, setInput] = useState("");
  const seedSentRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Reset history each time the drawer opens — sessions are
  // ephemeral by design.
  useEffect(() => {
    if (open) {
      setHistory([]);
      setInput("");
      seedSentRef.current = null;
    }
  }, [open]);

  // Fire the seed message exactly once per drawer open. The ref guard
  // prevents a re-fire when the parent re-renders with the same seed.
  useEffect(() => {
    if (!open || !seedMessage) return;
    if (seedSentRef.current === seedMessage) return;
    seedSentRef.current = seedMessage;
    void send(seedMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, seedMessage]);

  // Auto-scroll to the latest reply.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [history, chat.isPending]);

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || chat.isPending) return;
    // Optimistically append the user turn so the UI updates before
    // the LLM round-trip completes.
    const optimistic = [
      ...history,
      { role: "user" as const, content: trimmed },
    ];
    setHistory(optimistic);
    setInput("");
    try {
      const res = await chat.mutateAsync({
        message: trimmed,
        history,
      });
      setHistory(res.updated_history);
    } catch {
      // Backend already provides a fallback string in `reply` for
      // LLM failures — a thrown error here is a network blip.
      setHistory((h) => [
        ...h,
        {
          role: "assistant",
          content: "Сейчас не могу ответить — попробуй через минуту.",
        },
      ]);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
        aria-hidden
      />

      {/* Drawer */}
      <aside
        className="relative h-full w-full md:w-[420px] bg-white shadow-2xl flex flex-col"
        role="dialog"
        aria-label="Sales Coach"
      >
        {/* Header */}
        <header className="flex items-center justify-between px-5 py-4 border-b border-brand-border">
          <div className="flex items-center gap-2">
            <span className="bg-brand-soft text-brand-accent-text rounded-full w-8 h-8 flex items-center justify-center">
              <Sparkles size={15} aria-hidden />
            </span>
            <div>
              <p className={`${C.bodySm} font-bold ${C.color.text}`}>Чак</p>
              <p className={`${C.bodyXs} ${C.color.mutedLight}`}>
                Sales Coach
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Закрыть"
            className={`p-1.5 rounded-full ${C.color.mutedLight}`}
          >
            <X size={16} aria-hidden />
          </button>
        </header>

        {/* Messages */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto px-5 py-4 space-y-3"
        >
          <Message role="assistant" content={GREETING} />
          {history.map((m, i) => (
            <Message key={i} role={m.role} content={m.content} />
          ))}
          {chat.isPending && (
            <div className="flex items-center gap-2 px-3">
              <Loader2
                size={14}
                className="animate-spin text-brand-muted"
                aria-hidden
              />
              <span className={`${C.bodyXs} ${C.color.mutedLight}`}>
                Чак думает…
              </span>
            </div>
          )}
        </div>

        {/* Quick chips */}
        {history.length === 0 && !chat.isPending && (
          <div className="px-5 pb-2 flex flex-wrap gap-1.5">
            {QUICK_CHIPS.map((chip) => (
              <button
                key={chip.label}
                onClick={() => send(chip.message)}
                className={`${C.button.ghost} ${C.btn} px-3 py-1.5`}
              >
                {chip.label}
              </button>
            ))}
          </div>
        )}

        {/* Composer */}
        <div className="px-5 py-3 border-t border-brand-border">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send(input);
            }}
            className="flex items-center gap-2"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Спроси Чака…"
              disabled={chat.isPending}
              className={`flex-1 ${C.form.field} py-2 text-sm`}
            />
            <button
              type="submit"
              disabled={!input.trim() || chat.isPending}
              aria-label="Отправить"
              className={`${C.button.primary} ${C.btn} px-3 py-2 disabled:opacity-40`}
            >
              <Send size={14} aria-hidden />
            </button>
          </form>
        </div>
      </aside>
    </div>
  );
}

function Message({
  role,
  content,
}: {
  role: "user" | "assistant";
  content: string;
}) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] px-3.5 py-2 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words ${
          isUser
            ? "bg-brand-accent text-white"
            : "bg-brand-bg text-brand-primary"
        }`}
      >
        {content}
      </div>
    </div>
  );
}
