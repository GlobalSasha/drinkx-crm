"use client";
// LostModal — Sprint 2.6 G3.
//
// Replaces the prior `window.confirm` + `window.prompt` pair on the
// «Перевести в Проигран» action with a styled modal matching the rest
// of the LeadCard's modal surface (GateModal / TransferModal). Reason
// is REQUIRED — the backend rejects a close-as-lost with no reason
// (plan 007); the confirm button stays disabled until one is typed.
//
// Same shape contract as GateModal: parent owns `onClose` / `onSuccess`
// callbacks. The mutation lives at the parent (LeadCard) so error
// handling stays in one place.
//
// The reason is picked from a fixed list (so refusals can be grouped
// later) plus an optional comment; stored as «Причина — комментарий» in
// `lost_reason`. «Другое» needs the comment.
import { useState } from "react";
import { Loader2, X } from "lucide-react";

import { useMoveStage } from "@/lib/hooks/use-leads";
import type { Stage } from "@/lib/types";
import { Modal } from "@/components/ui/Modal";

export const LOST_REASONS = [
  "Не устроила цена",
  "Не устроили сроки",
  "Нужен НДС",
  "Нужен лизинг",
  "Не готов платить за обучение",
  "Нет дистрибьютора в регионе",
  "Не готов покупать сейчас",
  "Просто интересовался",
  "Передумал",
  "Непрофильный клиент",
  "Другое",
] as const;

const OTHER = "Другое";

interface Props {
  leadId: string;
  lostStage: Stage;
  companyName: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function LostModal({
  leadId,
  lostStage,
  companyName,
  onClose,
  onSuccess,
}: Props) {
  const [reason, setReason] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const moveStage = useMoveStage();

  const note = comment.trim();
  const canConfirm = reason !== null && (reason !== OTHER || note.length > 0);

  function handleConfirm() {
    setError(null);
    moveStage.mutate(
      {
        leadId,
        body: {
          stage_id: lostStage.id,
          // Confirm is disabled until a reason is picked, so this is
          // always a real reason.
          lost_reason: note ? `${reason} — ${note}` : (reason ?? ""),
        },
      },
      {
        onSuccess: () => {
          onSuccess();
          onClose();
        },
        onError: (err) => {
          setError(err.message || "Не удалось закрыть лид.");
        },
      },
    );
  }

  return (
    <Modal open onClose={onClose} title="Закрыть как проигран?" dismissOnBackdrop={false}>
      <div className="-m-6">
        <div className="flex items-center justify-between px-5 py-4 border-b border-brand-border">
          <h3 className="text-base font-semibold">
            Закрыть как проигран
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-brand-muted hover:text-brand-primary p-1"
            aria-label="Закрыть"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <p className="text-sm text-brand-muted">
            Лид{" "}
            <span className="font-semibold text-brand-primary">{companyName}</span>{" "}
            уйдёт с доски воронки, но останется в базе вместе с причиной.
            Вернуть можно, переведя лид обратно в рабочий этап.
          </p>

          <fieldset>
            <legend className="text-xs font-mono uppercase tracking-wide text-brand-muted">
              Причина <span className="text-rose">*</span>
            </legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {LOST_REASONS.map((r) => {
                const active = reason === r;
                return (
                  <button
                    key={r}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setReason(r)}
                    className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                      active
                        ? "border-rose bg-rose/10 text-rose font-semibold"
                        : "border-brand-border bg-white text-brand-primary hover:border-brand-muted"
                    }`}
                  >
                    {r}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <div>
            <label
              htmlFor="lost-comment"
              className="text-xs font-mono uppercase tracking-wide text-brand-muted"
            >
              Комментарий{" "}
              {reason === OTHER ? <span className="text-rose">*</span> : "(необязательно)"}
            </label>
            <textarea
              id="lost-comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Что именно случилось — пригодится для разбора отказов"
              rows={3}
              className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 resize-none"
            />
          </div>

          {error && <p className="text-xs text-rose">{error}</p>}

          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={handleConfirm}
              disabled={moveStage.isPending || !canConfirm}
              className="inline-flex items-center gap-1.5 bg-rose text-white rounded-full px-4 py-2 text-sm font-semibold hover:bg-rose/90 disabled:opacity-40 transition duration-300"
            >
              {moveStage.isPending && (
                <Loader2 size={13} className="animate-spin" />
              )}
              Закрыть лид
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={moveStage.isPending}
              className="text-sm text-brand-muted hover:text-brand-primary disabled:opacity-40"
            >
              Отмена
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
