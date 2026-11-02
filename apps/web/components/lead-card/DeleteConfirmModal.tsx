"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { useDeleteLead } from "@/lib/hooks/use-lead";
import { ApiError } from "@/lib/api-client";
import { C } from "@/lib/design-system";
import { Modal } from "@/components/ui/Modal";

interface Props {
  leadId: string;
  companyName: string;
  onClose: () => void;
}

/**
 * One-click confirm. Delete is a soft delete (Trash, restorable by an
 * admin), so typing the company name was friction without protection.
 * On success, navigates back to /pipeline — the lead row is gone.
 */
export function DeleteConfirmModal({ leadId, companyName, onClose }: Props) {
  const del = useDeleteLead(leadId);
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

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
    <Modal open onClose={onClose} title="Удалить лид?" dismissOnBackdrop={false}>
      <>
        <div className="flex items-start gap-3 mb-4">
          <div className="p-2 rounded-full bg-rose/10 shrink-0">
            <AlertTriangle size={20} className="text-rose" />
          </div>
          <div>
            <h2 className={`type-card-title ${C.color.text}`}>
              Удалить лид?
            </h2>
            <p className={`type-caption ${C.color.muted} mt-1`}>
              «{companyName}» пропадёт из воронки и поиска вместе с
              контактами и задачами. Если удалили по ошибке, лид можно
              вернуть — напишите администратору.
            </p>
          </div>
        </div>

        {error && (
          <p className="type-caption text-rose mb-3">{error}</p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={del.isPending}
            className={`px-4 py-1.5 type-body font-semibold ${C.button.ghost} transition-opacity`}
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={del.isPending}
            className="px-4 py-1.5 type-body font-semibold bg-rose text-white rounded-full disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
          >
            {del.isPending ? "Удаление…" : "Удалить"}
          </button>
        </div>
      </>
    </Modal>
  );
}
