"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { useMe } from "@/lib/hooks/use-me";
import { useUsers } from "@/lib/hooks/use-users";
import { useLeads } from "@/lib/hooks/use-leads";
import { useCreateTask } from "@/lib/hooks/use-tasks";
import { UserSelect } from "@/components/ui/UserSelect";
import { apiErrorDetail } from "@/lib/api-error";
import { C } from "@/lib/design-system";
import type { LeadOut, MyTaskOut, TaskCreateIn } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (task: MyTaskOut) => void;
}

export function TaskCreateModal({ open, onClose, onCreated }: Props) {
  const { data: me } = useMe();
  const { data: usersData } = useUsers();
  const create = useCreateTask();

  const canAssignOthers = me?.role === "admin" || me?.role === "head";

  const [text, setText] = useState("");
  const [due, setDue] = useState("");
  const [assigneeId, setAssigneeId] = useState<string | null>(null);
  const [leadQuery, setLeadQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedLead, setSelectedLead] = useState<LeadOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Дефолт исполнителя — сам постановщик, как только известен /me.
  useEffect(() => {
    if (canAssignOthers && me?.id && assigneeId === null) {
      setAssigneeId(me.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canAssignOthers, me?.id]);

  // Дебаунс поиска лида — 300 мс, таймер чистим на unmount/смену запроса.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(leadQuery.trim()), 300);
    return () => clearTimeout(t);
  }, [leadQuery]);

  const { data: leadsData, isFetching: isFetchingLeads } = useLeads({
    q: debouncedQuery || undefined,
    workspace_search: true,
    page_size: 12,
  });
  const leadResults = debouncedQuery.length >= 2 ? (leadsData?.items ?? []) : [];

  function reset() {
    setText("");
    setDue("");
    setAssigneeId(canAssignOthers ? (me?.id ?? null) : null);
    setLeadQuery("");
    setDebouncedQuery("");
    setSelectedLead(null);
    setError(null);
  }

  // useCallback: Modal's focus-trap effect re-runs whenever this
  // reference changes — a fresh function on every keystroke would steal
  // focus back to the first focusable element (the close button).
  const handleClose = useCallback(() => {
    reset();
    onClose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose]);

  const disabled = !text.trim() || (canAssignOthers && !assigneeId) || create.isPending;

  async function handleSave() {
    if (disabled) return;
    setError(null);

    let iso: string | null = null;
    if (due) {
      const d = new Date(due); // datetime-local parsed in local time
      if (!Number.isNaN(d.getTime())) iso = d.toISOString();
    }

    const body: TaskCreateIn = { text: text.trim(), task_due_at: iso };
    if (canAssignOthers) body.assignee_user_id = assigneeId;
    if (selectedLead) body.lead_id = selectedLead.id;

    try {
      const task = await create.mutateAsync(body);
      onCreated(task);
      reset();
      onClose();
    } catch (err) {
      setError(apiErrorDetail(err, "Не удалось поставить задачу"));
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title="Новая задача" dismissOnBackdrop={false}>
      <div className="-m-6">
        <div className="flex items-center justify-between px-5 py-4 border-b border-brand-border">
          <h3 className="text-base font-bold">Новая задача</h3>
          <button
            type="button"
            onClick={handleClose}
            className="text-brand-muted hover:text-brand-primary p-1"
            aria-label="Закрыть"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <div>
            <label className="text-xs font-mono uppercase tracking-wide text-brand-muted">
              Текст задачи
            </label>
            <input
              autoFocus
              value={text}
              maxLength={2000}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !disabled) void handleSave();
              }}
              placeholder="Что нужно сделать"
              className={`mt-1 ${C.form.field}`}
            />
          </div>

          <div>
            <label className="text-xs font-mono uppercase tracking-wide text-brand-muted">
              Срок и время
            </label>
            <input
              type="datetime-local"
              value={due}
              onChange={(e) => setDue(e.target.value)}
              aria-label="Срок и время"
              className={`mt-1 ${C.form.field}`}
            />
            {due && (
              <button
                type="button"
                onClick={() => setDue("")}
                className="mt-1 text-xs text-brand-muted hover:text-brand-primary"
              >
                Очистить срок
              </button>
            )}
          </div>

          {canAssignOthers && (
            <div>
              <label className="text-xs font-mono uppercase tracking-wide text-brand-muted">
                Исполнитель
              </label>
              <UserSelect
                value={assigneeId}
                onChange={setAssigneeId}
                users={usersData?.items ?? []}
                meId={me?.id}
                aria-label="Исполнитель"
                className="mt-1"
              />
            </div>
          )}

          <div>
            <label className="text-xs font-mono uppercase tracking-wide text-brand-muted">
              Лид (необязательно)
            </label>
            {selectedLead ? (
              <div className="mt-1 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-brand-panel type-caption text-brand-muted-strong">
                {selectedLead.company_name}
                <button
                  type="button"
                  onClick={() => setSelectedLead(null)}
                  aria-label="Убрать лид"
                  className="text-brand-muted hover:text-brand-primary"
                >
                  <X size={12} />
                </button>
              </div>
            ) : (
              <>
                <input
                  value={leadQuery}
                  onChange={(e) => setLeadQuery(e.target.value)}
                  placeholder="Найти лид по компании…"
                  className={`mt-1 ${C.form.field}`}
                />
                {debouncedQuery.length >= 2 && isFetchingLeads && (
                  <p className="mt-1 type-caption text-brand-muted">Ищем…</p>
                )}
                {debouncedQuery.length >= 2 &&
                  !isFetchingLeads &&
                  leadResults.length === 0 && (
                    <p className="mt-1 type-caption text-brand-muted">
                      Не нашли. Задачу можно поставить без лида
                    </p>
                  )}
                {leadResults.length > 0 && (
                  <div className="mt-1 max-h-40 overflow-y-auto flex flex-col gap-0.5 border border-brand-border rounded-xl p-1">
                    {leadResults.map((lead) => (
                      <button
                        key={lead.id}
                        type="button"
                        onClick={() => {
                          setSelectedLead(lead);
                          setLeadQuery("");
                        }}
                        className="text-left px-2 py-1.5 rounded-lg hover:bg-brand-bg transition-colors type-caption text-brand-muted-strong"
                      >
                        {lead.company_name} · {lead.city || "—"}
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          {error && <p className="text-xs text-rose">{error}</p>}

          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={disabled}
              className={`${C.button.primary} type-body px-4 py-2 disabled:opacity-40`}
            >
              {create.isPending && (
                <Loader2 size={13} className="animate-spin inline-block mr-1.5" />
              )}
              {create.isPending ? "Ставим…" : "Поставить"}
            </button>
            <button
              type="button"
              onClick={handleClose}
              disabled={create.isPending}
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
