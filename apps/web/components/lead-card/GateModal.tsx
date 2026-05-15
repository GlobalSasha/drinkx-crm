"use client";
import { useState } from "react";
import { X, AlertTriangle, CheckSquare, Square } from "lucide-react";
import { useMoveStage } from "@/lib/hooks/use-leads";
import type { Stage, GateViolationOut } from "@/lib/types";
import { DEFAULT_GATE_CRITERIA } from "@/lib/types";
import { ApiError } from "@/lib/api-client";
import { Modal } from "@/components/ui/Modal";

interface Props {
  leadId: string;
  targetStage: Stage;
  onClose: () => void;
  onSuccess: () => void;
}

export function GateModal({ leadId, targetStage, onClose, onSuccess }: Props) {
  const criteria =
    targetStage.gate_criteria_json?.length > 0
      ? targetStage.gate_criteria_json
      : (DEFAULT_GATE_CRITERIA[targetStage.position] ?? []);

  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const [forceSkip, setForceSkip] = useState(false);
  const [skipReason, setSkipReason] = useState("");
  const [violations, setViolations] = useState<GateViolationOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  const moveStage = useMoveStage();

  function toggle(i: number) {
    setChecked((prev) => ({ ...prev, [i]: !prev[i] }));
  }

  function handleSubmit() {
    setError(null);
    setViolations([]);

    if (forceSkip && !skipReason.trim()) {
      setError("Укажите причину принудительного перемещения");
      return;
    }

    moveStage.mutate(
      {
        leadId,
        body: {
          stage_id: targetStage.id,
          gate_skipped: forceSkip,
          skip_reason: forceSkip ? skipReason.trim() : null,
        },
      },
      {
        onSuccess: () => {
          onSuccess();
          onClose();
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 409) {
            const detail = err.body as { message?: string; violations?: GateViolationOut[] };
            if (detail?.violations) {
              setViolations(detail.violations);
            }
            setError(detail?.message ?? "Переход заблокирован");
          } else {
            setError("Ошибка при перемещении");
          }
        },
      }
    );
  }

  return (
    <Modal open onClose={onClose} title="Переход в стадию">
      <div className="-m-6 p-6 max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-bold tracking-tight text-ink">
                Переход в стадию
              </h2>
              <p
                className="text-sm font-semibold mt-0.5"
                style={{ color: targetStage.color }}
              >
                {targetStage.name}
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-black/5 text-muted transition-colors"
            >
              <X size={18} />
            </button>
          </div>

          {/* Gate criteria checklist */}
          {criteria.length > 0 && (
            <div className="mb-4">
              <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 mb-2">
                Критерии перехода
              </p>
              <div className="space-y-2">
                {criteria.map((criterion, i) => {
                  const violated = violations.some((v) =>
                    v.message.includes(criterion)
                  );
                  return (
                    <button
                      key={i}
                      onClick={() => toggle(i)}
                      className={`flex items-start gap-2.5 w-full text-left p-2.5 rounded-xl transition-colors ${
                        violated
                          ? "bg-rose/5 border border-rose/20"
                          : checked[i]
                          ? "bg-success/5"
                          : "hover:bg-canvas"
                      }`}
                    >
                      {checked[i] ? (
                        <CheckSquare size={16} className="text-success shrink-0 mt-0.5" />
                      ) : violated ? (
                        <AlertTriangle size={16} className="text-rose shrink-0 mt-0.5" />
                      ) : (
                        <Square size={16} className="text-muted-3 shrink-0 mt-0.5" />
                      )}
                      <span
                        className={`text-sm ${
                          violated
                            ? "text-rose"
                            : checked[i]
                            ? "text-success"
                            : "text-ink"
                        }`}
                      >
                        {criterion}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Violation errors */}
          {violations.length > 0 && (
            <div className="mb-4 bg-rose/5 border border-rose/20 rounded-xl px-4 py-3 space-y-1">
              {violations.map((v, i) => (
                <p key={i} className="text-xs text-rose">
                  {v.message}
                </p>
              ))}
            </div>
          )}

          {/* Force skip toggle */}
          <div className="mb-4 pt-2 border-t border-black/5">
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={forceSkip}
                onChange={(e) => setForceSkip(e.target.checked)}
                className="w-4 h-4 accent-rose rounded"
              />
              <span className="text-sm font-medium text-rose">
                Force-move (пропустить gate)
              </span>
            </label>
            {forceSkip && (
              <textarea
                value={skipReason}
                onChange={(e) => setSkipReason(e.target.value)}
                placeholder="Укажите причину..."
                rows={2}
                className="mt-2 w-full px-3 py-2 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 focus:bg-white resize-none transition-all"
              />
            )}
          </div>

          {error && (
            <p className="text-xs text-rose mb-3">{error}</p>
          )}

          {/* Actions */}
          <div className="flex gap-2 justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-pill text-sm font-semibold text-muted bg-canvas hover:bg-canvas-2 transition-all"
            >
              Отмена
            </button>
            <button
              onClick={handleSubmit}
              disabled={moveStage.isPending}
              className="px-5 py-2 rounded-pill text-sm font-semibold bg-ink text-white transition-all hover:bg-ink/90 disabled:opacity-50"
            >
              {moveStage.isPending ? "..." : "Переместить"}
            </button>
          </div>
      </div>
    </Modal>
  );
}
