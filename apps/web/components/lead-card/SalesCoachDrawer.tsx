"use client";

// Sprint 3.1 Phase D — Sales Coach chat drawer.
//
// Right-side slide-over with:
//   - Static greeting from Чак at the top (no LLM call on open).
//   - Quick chips for the four canonical questions in the agent
//     skill (`docs/skills/lead-ai-agent-skill.md` §8 «Quick chips»).
//   - Free-text input + send.
//   - In-memory history (the spec is explicit: «не персистится —
//     достаточно для сессии» — closing the drawer drops it).
//
// FAB toggle lives on the LeadCard. We render a backdrop + slide-
// over panel; clicking the backdrop or pressing Esc closes.

import { useEffect, useRef, useState } from "react";
import { Bot, Loader2, Send, X } from "lucide-react";

import { useAgentChat } from "@/lib/hooks/use-lead-agent";
import type { AgentChatMessage } from "@/lib/types";
import { C } from "@/lib/design-system";


const QUICK_CHIPS = [
  "Что делать дальше?",
  "Напиши follow-up письмо",
  "Разбери возражение клиента",
  "Готов ли лид к переходу на следующую стадию?",
];

const GREETING =
  "Привет! Я Чак — твой ассистент по этому лиду. Спрашивай что делать, " +
  "пиши черновики, разбирай возражения. Видеть могу только активности " +
  "по этому конкретному лиду.";


export function SalesCoachDrawer({
  leadId,
  open,
  onClose,
}: {
  leadId: string;
  open: boolean;
  onClose: () => void;
}) {
  const chat = useAgentChat(leadId);
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<AgentChatMessage[]>([]);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Drop the conversation when the drawer closes — explicit per the
  // skill. Re-opening starts fresh.
  useEffect(() => {
    if (!open) {
      setHistory([]);
      setInput("");
      chat.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Esc closes
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Auto-scroll to the newest message after each turn.
  useEffect(() => {
    if (!open) return;
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history.length, chat.isPending, open]);

  function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || chat.isPending) return;
    setInput("");
    // Optimistic: append the user turn before the LLM round-trip
    // so the input doesn't feel laggy on the wire.
    const optimistic: AgentChatMessage = { role: "user", content: trimmed };
    const optimisticHistory = [...history, optimistic];
    setHistory(optimisticHistory);

    chat.mutate(
      { message: trimmed, history },
      {
        onSuccess: (resp) => {
          // Server returns the trimmed-to-20 history; trust it.
          setHistory(resp.updated_history);
        },
        onError: () => {
          // Append a synthetic assistant turn so the user sees the
          // failure in-line instead of a silent roll-back.
          setHistory([
            ...optimisticHistory,
            {
              role: "assistant",
              content:
                "Не получилось ответить — попробуй ещё раз через минуту.",
            },
          ]);
        },
      },
    );
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <button
        type="button"
        className="absolute inset-0 bg-brand-primary/20 backdrop-blur-sm"
        onClick={onClose}
        aria-label="Закрыть Sales Coach"
        tabIndex={-1}
      />

      {/* Panel */}
      <aside className="relative ml-auto h-full w-full max-w-md bg-white shadow-soft flex flex-col">
        {/* Header */}
        <header className="px-5 py-4 border-b border-brand-border flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-brand-soft flex items-center justify-center shrink-0">
            <Bot size={16} className="text-brand-accent-text" />
          </div>
          <div className="flex-1 min-w-0">
            <div className={`${C.bodySm} font-bold text-brand-primary`}>
              Чак · Sales Coach
            </div>
            <div className={`${C.bodyXs} text-brand-muted truncate`}>
              Контекст этого лида · история не сохраняется
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-brand-muted hover:text-brand-primary p-1 -m-1"
            aria-label="Закрыть"
          >
            <X size={18} />
          </button>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {/* Static greeting — never goes through the LLM. */}
          <Message role="assistant" content={GREETING} />

          {history.map((m, i) => (
            <Message key={i} role={m.role} content={m.content} />
          ))}

          {chat.isPending && (
            <div className="flex items-center gap-2 px-3 py-2 text-brand-muted">
              <Loader2 size={12} className="animate-spin" />
              <span className={C.bodyXs}>Чак думает...</span>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick chips — only shown before the first user turn so they
            don't crowd a long conversation. */}
        {history.length === 0 && (
          <div className="px-5 pb-2 flex flex-wrap gap-1.5">
            {QUICK_CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => send(chip)}
                disabled={chat.isPending}
                className={`${C.bodyXs} px-3 py-1.5 rounded-full border border-brand-border bg-brand-bg text-brand-primary hover:border-brand-accent transition disabled:opacity-50`}
              >
                {chip}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="px-5 py-3 border-t border-brand-border flex items-end gap-2"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            rows={1}
            placeholder="Спросить Чака..."
            className={`flex-1 resize-none ${C.bodySm} px-3 py-2 rounded-2xl bg-brand-bg border border-brand-border focus:border-brand-accent outline-none text-brand-primary placeholder:text-brand-muted min-h-[40px] max-h-[120px]`}
          />
          <button
            type="submit"
            disabled={!input.trim() || chat.isPending}
            className="shrink-0 w-10 h-10 rounded-full bg-brand-accent text-white flex items-center justify-center hover:opacity-90 disabled:opacity-30 transition"
            aria-label="Отправить"
          >
            {chat.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
          </button>
        </form>
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
        className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl ${C.bodySm} whitespace-pre-wrap break-words ${
          isUser
            ? "bg-brand-accent text-white"
            : "bg-brand-bg text-brand-primary border border-brand-border"
        }`}
      >
        {content}
      </div>
    </div>
  );
}
