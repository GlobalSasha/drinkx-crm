"use client";
// LostModal — Sprint 2.6 G3.
//
// Replaces the prior `window.confirm` + `window.prompt` pair on the
// «Перевести в Проигран» action with a styled modal matching the rest
// of the LeadCard's modal surface (GateModal / TransferModal). Reason
// is OPTIONAL — the backend accepts NULL — but the UI nudges the
// manager to fill it in for retrospectives.
//
// Same shape contract as GateModal: parent owns `onClose` / `onSuccess`
// callbacks. The mutation lives at the parent (LeadCard) so error
// handling stays in one place.
import { useState } from "react";
import { Loader2, X } from "lucide-react";

import { useMoveStage } from "@/lib/hooks/use-leads";
import type { Stage } from "@/lib/types";

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
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const moveStage = useMoveStage();

  function handleConfirm() {
    setError(null);
    moveStage.mutate(
      {
        leadId,
        body: {
          stage_id: lostStage.id,
          // Empty string → NULL on the backend (lost_reason is
          // nullable). Trim defensive in case the manager typed
          // whitespace in the form.
          lost_reason: reason.trim() || null,
        },
      },
      {
        onSuccess: () => {
          onSuccess();
          onClose();
        },
        onError: (err) => {
          setError(err.message || "Не удалось перевести в Проигран.");
        },
      },
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-black/5">
          <h3 className="text-base font-extrabold">
            Перевести в «Проигран»?
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-muted hover:text-ink p-1"
            aria-label="Закрыть"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <p className="text-sm text-muted">
            Лид{" "}
            <span className="font-semibold text-ink">{companyName}</span>{" "}
            будет помечен как закрытый. Это действие можно отменить
            ручным переводом обратно в активную стадию.
          </p>

          <div>
            <label className="text-[11px] font-mono uppercase tracking-wide text-muted-3">
              Причина <span className="text-muted-3">(необязательно)</span>
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Например: бюджет не подтверждён, конкурент выиграл, клиент закрыл проект"
              rows={3}
              className="mt-1 w-full bg-canvas border border-black/10 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent resize-none"
            />
            <p className="text-[10px] text-muted-3 mt-1">
              Помогает с ретроспективой по проигранным сделкам.
            </p>
          </div>

          {error && <p className="text-xs text-rose">{error}</p>}

          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={handleConfirm}
              disabled={moveStage.isPending}
              className="inline-flex items-center gap-1.5 bg-rose text-white rounded-pill px-4 py-2 text-sm font-semibold hover:bg-rose/90 disabled:opacity-40 transition-all duration-300"
            >
              {moveStage.isPending && (
                <Loader2 size={13} className="animate-spin" />
              )}
              Подтвердить
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={moveStage.isPending}
              className="text-sm text-muted hover:text-ink disabled:opacity-40"
            >
              Отмена
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
