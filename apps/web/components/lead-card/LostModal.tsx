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
import { useState } from "react";
import { Loader2, X } from "lucide-react";

import { useMoveStage } from "@/lib/hooks/use-leads";
import type { Stage } from "@/lib/types";
import { Modal } from "@/components/ui/Modal";

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
          // Required: confirm is disabled until a non-empty reason is
          // typed, so this is always a real reason.
          lost_reason: reason.trim(),
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
    <Modal open onClose={onClose} title="Перевести в Проигран?" dismissOnBackdrop={false}>
      <div className="-m-6">
        <div className="flex items-center justify-between px-5 py-4 border-b border-brand-border">
          <h3 className="text-base font-bold">
            Перевести в «Проигран»?
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
            будет помечен как закрытый. Это действие можно отменить
            ручным переводом обратно в активную стадию.
          </p>

          <div>
            <label className="text-xs font-mono uppercase tracking-wide text-brand-muted">
              Причина <span className="text-rose">*</span>
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Например: бюджет не подтверждён, конкурент выиграл, клиент закрыл проект"
              rows={3}
              className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 resize-none"
            />
            <p className="text-2xs text-brand-muted mt-1">
              Помогает с ретроспективой по проигранным сделкам.
            </p>
          </div>

          {error && <p className="text-xs text-rose">{error}</p>}

          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={handleConfirm}
              disabled={moveStage.isPending || !reason.trim()}
              className="inline-flex items-center gap-1.5 bg-rose text-white rounded-full px-4 py-2 text-sm font-semibold hover:bg-rose/90 disabled:opacity-40 transition-all duration-300"
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
