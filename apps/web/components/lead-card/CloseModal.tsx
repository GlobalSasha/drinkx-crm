"use client";
import { useState } from "react";
import { Trophy, XCircle } from "lucide-react";
import { useMoveStage } from "@/lib/hooks/use-leads";
import type { Stage } from "@/lib/types";
import { C } from "@/lib/design-system";
import { Modal } from "@/components/ui/Modal";

interface Props {
  leadId: string;
  wonStage: Stage | null;
  lostStage: Stage | null;
  onClose: () => void;
  onSuccess: () => void;
  onLostFlow: () => void;
}

/**
 * Replaces the separate Won / Lost buttons. Manager picks an outcome,
 * Won goes straight through `moveStage`; Lost defers to `LostModal` so
 * the manager can supply a reason.
 */
export function CloseModal({
  leadId,
  wonStage,
  lostStage,
  onClose,
  onSuccess,
  onLostFlow,
}: Props) {
  const moveStage = useMoveStage();
  const [pendingChoice, setPendingChoice] = useState<"won" | "lost" | null>(null);

  function handleWon() {
    if (!wonStage) return;
    setPendingChoice("won");
    moveStage.mutate(
      { leadId, body: { stage_id: wonStage.id } },
      {
        onSuccess: () => {
          setPendingChoice(null);
          onSuccess();
          onClose();
        },
        onError: () => setPendingChoice(null),
      },
    );
  }

  function handleLost() {
    onClose();
    onLostFlow();
  }

  return (
    <Modal open onClose={onClose} title="Закрыть лид" dismissOnBackdrop={false}>
      <>
        <h2 className={`type-card-title ${C.color.text} mb-1`}>
          Закрыть лид
        </h2>
        <p className={`type-caption ${C.color.muted} mb-5`}>
          Выберите итог сделки. Действие переводит лид в финальную стадию.
        </p>

        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={handleWon}
            disabled={!wonStage || pendingChoice !== null}
            className="flex flex-col items-center gap-2 py-5 rounded-2xl border-2 border-success/20 bg-success/5 hover:bg-success/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Trophy size={28} className="text-success" />
            <span className="type-caption font-semibold text-success">
              {pendingChoice === "won" ? "Сохранение…" : "Выиграна"}
            </span>
          </button>
          <button
            type="button"
            onClick={handleLost}
            disabled={!lostStage}
            className="flex flex-col items-center gap-2 py-5 rounded-2xl border-2 border-rose/20 bg-rose/5 hover:bg-rose/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <XCircle size={28} className="text-rose" />
            <span className="type-caption font-semibold text-rose">Проиграна</span>
          </button>
        </div>

        <div className="flex justify-end mt-5">
          <button
            type="button"
            onClick={onClose}
            disabled={pendingChoice !== null}
            className={`type-caption font-semibold ${C.color.muted} hover:${C.color.text} transition-colors px-3 py-1.5`}
          >
            Отмена
          </button>
        </div>
      </>
    </Modal>
  );
}
