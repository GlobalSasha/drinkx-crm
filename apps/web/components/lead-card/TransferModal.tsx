"use client";
import { useState } from "react";
import { X, ArrowRight, AlertTriangle } from "lucide-react";
import { useTransferLead } from "@/lib/hooks/use-leads";
import { ApiError } from "@/lib/api-client";

interface Props {
  leadId: string;
  currentAssignedTo: string | null;
  onClose: () => void;
  onSuccess: () => void;
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Передача лида другому менеджеру.
 *
 * NOTE: there is no `/api/users` listing endpoint yet, so the manager
 * pastes the recipient's UUID directly. The backend already validates
 * that the user exists in the same workspace and returns 400 if not —
 * this modal surfaces that error inline. A user-picker can replace the
 * raw UUID input once a workspace-users endpoint lands.
 */
export function TransferModal({ leadId, currentAssignedTo, onClose, onSuccess }: Props) {
  const transfer = useTransferLead();
  const [toUserId, setToUserId] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const trimmed = toUserId.trim();
  const isValidUuid = UUID_RE.test(trimmed);
  const isSameUser = !!currentAssignedTo && trimmed === currentAssignedTo;
  const canSubmit = isValidUuid && !isSameUser && !transfer.isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!canSubmit) {
      if (!isValidUuid) setError("Введите валидный UUID получателя");
      else if (isSameUser) setError("Лид уже принадлежит этому пользователю");
      return;
    }

    transfer.mutate(
      { leadId, to_user_id: trimmed, comment: comment.trim() || null },
      {
        onSuccess: () => {
          onSuccess();
          onClose();
        },
        onError: (err) => {
          if (err instanceof ApiError) {
            const detail = err.body as { detail?: string } | undefined;
            setError(detail?.detail ?? `Ошибка ${err.status}`);
          } else {
            setError("Не удалось передать лид");
          }
        },
      },
    );
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-50 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <form
          onSubmit={handleSubmit}
          className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-md p-6 max-h-[90vh] overflow-y-auto"
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-extrabold tracking-tight text-ink">
                Передать лид
              </h2>
              <p className="text-xs text-muted-2 mt-0.5">
                Новый владелец увидит лид в своём списке и получит уведомление.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-black/5 text-muted transition-colors shrink-0"
              aria-label="Закрыть"
            >
              <X size={18} />
            </button>
          </div>

          {/* Recipient UUID */}
          <div className="mb-3">
            <label
              htmlFor="transfer-to-user"
              className="block font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 mb-1.5"
            >
              UUID получателя
            </label>
            <input
              id="transfer-to-user"
              type="text"
              value={toUserId}
              onChange={(e) => setToUserId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              autoComplete="off"
              autoFocus
              spellCheck={false}
              className="w-full px-3 py-2 text-sm font-mono bg-canvas border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 focus:bg-white transition-all"
            />
            <p className="text-[11px] text-muted-3 mt-1">
              Спросите получателя в Settings → Profile (или у админа). Список
              пользователей появится в Phase 2.
            </p>
          </div>

          {/* Optional comment */}
          <div className="mb-4">
            <label
              htmlFor="transfer-comment"
              className="block font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 mb-1.5"
            >
              Комментарий <span className="text-muted-3">(необязательно)</span>
            </label>
            <textarea
              id="transfer-comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Например: «Уехал в отпуск, передаю на твою территорию»"
              rows={2}
              maxLength={500}
              className="w-full px-3 py-2 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 focus:bg-white resize-none transition-all"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="mb-3 flex items-start gap-2 bg-rose/5 border border-rose/20 rounded-xl px-3 py-2">
              <AlertTriangle size={14} className="text-rose shrink-0 mt-0.5" />
              <p className="text-xs text-rose">{error}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-pill text-sm font-semibold text-muted bg-canvas hover:bg-canvas-2 transition-all"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="inline-flex items-center gap-1.5 px-5 py-2 rounded-pill text-sm font-semibold bg-ink text-white transition-all hover:bg-ink/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {transfer.isPending ? "..." : (
                <>
                  Передать
                  <ArrowRight size={13} />
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
