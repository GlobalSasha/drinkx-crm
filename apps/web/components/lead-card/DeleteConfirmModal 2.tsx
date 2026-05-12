"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { useDeleteLead } from "@/lib/hooks/use-lead";
import { ApiError } from "@/lib/api-client";
import { C } from "@/lib/design-system";

interface Props {
  leadId: string;
  companyName: string;
  onClose: () => void;
}

/**
 * Two-step confirm: manager must type the company name to enable Delete.
 * On success, navigates back to /pipeline — the lead row is gone.
 */
export function DeleteConfirmModal({ leadId, companyName, onClose }: Props) {
  const del = useDeleteLead(leadId);
  const router = useRouter();
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);

  const ok = typed.trim().toLowerCase() === companyName.trim().toLowerCase();

  function handleDelete() {
    setError(null);
    del.mutate(undefined, {
      onSuccess: () => router.push("/pipeline"),
      onError: (err) => {
        if (err instanceof ApiError && err.status === 404) {
          setError("Лид уже удалён");
        } else {
          setError("Не удалось удалить лид");
        }
      },
    });
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-soft">
        <div className="flex items-start gap-3 mb-4">
          <div className="p-2 rounded-full bg-rose/10 shrink-0">
            <AlertTriangle size={20} className="text-rose" />
          </div>
          <div>
            <h2 className={`${C.cardTitle} font-bold ${C.color.text}`}>
              Удалить лид?
            </h2>
            <p className={`${C.bodySm} ${C.color.muted} mt-1`}>
              Действие нельзя отменить. Все связанные контакты, активности
              и follow-up&apos;ы будут удалены вместе с лидом.
            </p>
          </div>
        </div>

        <div className="mb-4">
          <label
            htmlFor="confirm-delete-name"
            className={`${C.bodyXs} font-mono uppercase tracking-wider ${C.color.muted} block mb-1.5`}
          >
            Введите название компании для подтверждения
          </label>
          <input
            id="confirm-delete-name"
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={companyName}
            className={`w-full px-3 py-2 ${C.bodySm} bg-white border border-brand-border rounded-xl outline-none focus:border-rose transition-colors`}
            autoFocus
          />
        </div>

        {error && (
          <p className={`${C.bodySm} text-rose mb-3`}>{error}</p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={del.isPending}
            className={`px-4 py-1.5 ${C.btnLg} font-semibold ${C.button.ghost} transition-opacity`}
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={!ok || del.isPending}
            className={`px-4 py-1.5 ${C.btnLg} font-semibold bg-rose text-white rounded-full disabled:opacity-40 disabled:cursor-not-allowed transition-opacity`}
          >
            {del.isPending ? "Удаление…" : "Удалить"}
          </button>
        </div>
      </div>
    </div>
  );
}
