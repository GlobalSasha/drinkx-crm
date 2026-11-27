"use client";

import { useEffect } from "react";
import type { CallOutcome } from "@/lib/call-outcome";

const OPTIONS: { key: CallOutcome; label: string }[] = [
  { key: "reached", label: "Дозвонился" },
  { key: "no_answer", label: "Не дозвонился" },
  { key: "call_back", label: "Перезвонить" },
];

/** Bottom sheet after a call: one tap fills the composer, the manager
 *  edits and sends. Nothing is saved from here. */
export function CallOutcomeSheet({
  company,
  onPick,
  onClose,
}: {
  company: string;
  onPick: (outcome: CallOutcome) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center md:justify-center">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="call-outcome-title"
        className="relative w-full md:max-w-sm bg-white rounded-t-card md:rounded-card shadow-overlay px-4 pt-6 max-h-[90dvh] overflow-y-auto"
        style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
      >
        <h2 id="call-outcome-title" className="type-card-title text-brand-primary">
          Как прошёл звонок?
        </h2>
        <p className="type-caption text-brand-muted mt-1 truncate">{company}</p>
        <div className="flex flex-col gap-2 mt-4">
          {OPTIONS.map((o) => (
            <button
              key={o.key}
              type="button"
              onClick={() => onPick(o.key)}
              className="min-h-11 w-full rounded-full border border-brand-border bg-white type-button text-brand-primary active:scale-[0.96] transition-transform"
            >
              {o.label}
            </button>
          ))}
          <button
            type="button"
            onClick={onClose}
            className="min-h-11 w-full rounded-full type-button text-brand-muted"
          >
            Не сейчас
          </button>
        </div>
      </div>
    </div>
  );
}
