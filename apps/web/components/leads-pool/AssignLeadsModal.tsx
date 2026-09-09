"use client";

import { useState } from "react";
import { Loader2, X } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { UserSelect } from "@/components/ui/UserSelect";
import { useUsers } from "@/lib/hooks/use-users";
import { useMe } from "@/lib/hooks/use-me";
import { useAssignLeads } from "@/lib/hooks/use-leads";
import { apiErrorDetail } from "@/lib/api-error";
import { C } from "@/lib/design-system";
import type { LeadAssignOut } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
  mode: "selected" | "topN";
  selectedIds: string[];
  /** id всех строк текущего `filtered` в порядке отображения. */
  visibleIds: string[];
  refetchPool: () => Promise<unknown>;
  onDone: (result: LeadAssignOut, recipientName: string) => void;
}

export function AssignLeadsModal({
  open,
  onClose,
  mode,
  selectedIds,
  visibleIds,
  refetchPool,
  onDone,
}: Props) {
  const usersQuery = useUsers();
  const meQuery = useMe();
  const assignMutation = useAssignLeads();
  const users = usersQuery.data?.items ?? [];

  const [managerId, setManagerId] = useState<string | null>(null);
  const [topN, setTopN] = useState<number>(() => Math.min(20, visibleIds.length));
  const [error, setError] = useState<string | null>(null);

  const isPending = assignMutation.isPending;

  const nInvalid = mode === "topN" && (topN < 1 || topN > visibleIds.length || !Number.isFinite(topN));
  const idsEmpty = mode === "selected" ? selectedIds.length === 0 : visibleIds.length === 0;
  const canSubmit = !!managerId && !nInvalid && !idsEmpty && !isPending;

  function handleClose() {
    if (isPending) return;
    onClose();
  }

  async function handleSubmit() {
    if (!canSubmit || !managerId) return;
    setError(null);
    try {
      // Перечитываем пул перед отправкой — иначе можно выдать то, что
      // менеджер только что взял себе.
      await refetchPool();
      const leadIds = mode === "selected" ? selectedIds : visibleIds.slice(0, topN);
      const recipient = users.find((u) => u.id === managerId);
      const recipientName = recipient?.name || recipient?.email || "";
      const result = await assignMutation.mutateAsync({
        to_user_id: managerId,
        mode: "ids",
        only_pool: true,
        lead_ids: leadIds,
      });
      onDone(result, recipientName);
      onClose();
    } catch (err) {
      setError(apiErrorDetail(err, "Не удалось выдать карточки"));
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Выдать карточки менеджеру"
      size="max-w-md"
      dismissOnBackdrop={false}
    >
      <div className="-m-6">
        <div className="flex items-center justify-between px-5 py-4 border-b border-brand-border">
          <h3 className="text-base font-bold">Выдать карточки менеджеру</h3>
          <button
            type="button"
            onClick={handleClose}
            disabled={isPending}
            className="text-brand-muted hover:text-brand-primary p-1 disabled:opacity-40"
            aria-label="Закрыть"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          {mode === "selected" ? (
            <p className="text-sm text-brand-primary">Карточек: {selectedIds.length}</p>
          ) : (
            <div>
              <label
                htmlFor="assign-top-n"
                className="text-xs font-mono uppercase tracking-wide text-brand-muted"
              >
                Сколько выдать
              </label>
              <input
                id="assign-top-n"
                type="number"
                min={1}
                max={visibleIds.length}
                value={topN}
                onChange={(e) => setTopN(Number(e.target.value))}
                className={`mt-1 ${C.form.field}`}
              />
              <p className="mt-1 text-xs text-brand-muted">
                Сейчас под фильтр подходит: {visibleIds.length}
              </p>
              <p className="mt-0.5 text-2xs text-brand-muted">
                Берутся первые N карточек в текущем порядке списка.
              </p>
            </div>
          )}

          <div>
            <label className="text-xs font-mono uppercase tracking-wide text-brand-muted">
              Менеджер
            </label>
            {usersQuery.isError ? (
              <p className="mt-1 text-xs text-rose">Не удалось загрузить список сотрудников</p>
            ) : (
              <UserSelect
                value={managerId}
                onChange={setManagerId}
                users={users}
                meId={meQuery.data?.id}
                allowEmpty
                emptyLabel="— выберите —"
                disabled={usersQuery.isLoading}
                aria-label="Менеджер"
                className="mt-1"
              />
            )}
          </div>

          {error && <p className="text-xs text-rose">{error}</p>}

          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit || usersQuery.isError}
              className={`${C.button.primary} type-body px-4 py-2 disabled:opacity-40`}
            >
              {isPending && <Loader2 size={13} className="animate-spin inline-block mr-1.5" />}
              {isPending ? "Выдаём…" : "Выдать"}
            </button>
            <button
              type="button"
              onClick={handleClose}
              disabled={isPending}
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
