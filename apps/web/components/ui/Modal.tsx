"use client";
import { useEffect, useId, useRef } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  /** Tailwind sizing — defaults to max-w-md. */
  size?: string;
  /** When false, clicking the backdrop does NOT dismiss the modal.
   *  Use for destructive flows where the manager must hit Cancel/Confirm. */
  dismissOnBackdrop?: boolean;
}

/**
 * Accessible modal primitive — Sprint audit fix.
 *
 *   - role="dialog" + aria-modal + aria-labelledby
 *   - Escape closes
 *   - Backdrop click closes (opt-out via dismissOnBackdrop=false)
 *   - Focus is moved into the dialog on open and restored on close
 *   - Background scroll is locked while open
 *
 * Title element is rendered for the modal heading and wired up via id —
 * pass plain text only.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  size = "max-w-md",
  dismissOnBackdrop = true,
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const headingId = useId();

  useEffect(() => {
    if (!open) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;

    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    document.addEventListener("keydown", handleKey);

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const dialog = dialogRef.current;
    if (dialog) {
      const first = dialog.querySelector<HTMLElement>(
        'input, textarea, select, button, [tabindex]:not([tabindex="-1"])',
      );
      (first ?? dialog).focus();
    }

    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = prevOverflow;
      if (previouslyFocused && document.body.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={dismissOnBackdrop ? onClose : undefined}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className={`bg-white rounded-3xl ${size} w-full p-6 shadow-soft outline-none`}
      >
        <h2 id={headingId} className="sr-only">
          {title}
        </h2>
        {children}
      </div>
    </div>
  );
}
