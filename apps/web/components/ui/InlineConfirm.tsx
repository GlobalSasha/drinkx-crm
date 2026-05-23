"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

/**
 * Inline two-step confirm. Replaces `window.confirm` for in-page
 * destructive actions where a full modal would be overkill.
 *
 *   <InlineConfirm
 *     onConfirm={() => deleteTask(id)}
 *     prompt={`Удалить задачу «${title}»?`}
 *     confirmLabel="Да, удалить"
 *     destructive
 *   >
 *     {(open) => (
 *       <Button variant="destructive" onClick={open}>
 *         Удалить
 *       </Button>
 *     )}
 *   </InlineConfirm>
 *
 * The render-prop is called with `open` — pass it as the trigger's
 * onClick. The component handles its own open/closed state.
 */
interface InlineConfirmProps {
  children: (open: () => void) => React.ReactNode;
  prompt: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void | Promise<void>;
  destructive?: boolean;
  busy?: boolean;
  className?: string;
}

export function InlineConfirm({
  children,
  prompt,
  confirmLabel = "Да",
  cancelLabel = "Отмена",
  onConfirm,
  destructive = false,
  busy = false,
  className,
}: InlineConfirmProps) {
  const [confirming, setConfirming] = React.useState(false);

  if (!confirming) {
    return <>{children(() => setConfirming(true))}</>;
  }

  const confirmClasses = destructive
    ? "text-rose bg-rose/10 hover:bg-rose/15"
    : "bg-brand-accent text-white hover:bg-brand-accent/90";

  return (
    <span
      role="group"
      aria-label="Подтверждение действия"
      className={cn("inline-flex items-center gap-1.5 text-xs", className)}
    >
      <span className="text-brand-muted">{prompt}</span>
      <button
        type="button"
        onClick={async (e) => {
          e.stopPropagation();
          try {
            await onConfirm();
          } finally {
            setConfirming(false);
          }
        }}
        disabled={busy}
        className={cn(
          "px-2 py-0.5 rounded-full font-semibold transition-colors disabled:opacity-50",
          confirmClasses,
        )}
      >
        {confirmLabel}
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setConfirming(false);
        }}
        disabled={busy}
        className="px-2 py-0.5 rounded-full text-brand-muted hover:bg-brand-panel transition-colors disabled:opacity-50"
      >
        {cancelLabel}
      </button>
    </span>
  );
}
