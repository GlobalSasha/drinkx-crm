"use client";
import { useState } from "react";
import {
  X,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Users,
  Crown,
  Mail,
  Phone,
  MapPin,
} from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { ApiError } from "@/lib/api-client";
import { useLeadDuplicates, useMergeLeads } from "@/lib/hooks/use-lead-duplicates";
import type { LeadOut } from "@/lib/types";

interface Props {
  leadId: string;
  masterName: string;
  onClose: () => void;
  onSuccess: (mergedCount: number) => void;
}

/**
 * Find-and-merge duplicates for a lead. The current lead is always the
 * master — the manager picks which surfaced candidates to absorb. Two
 * deliberate steps (select → confirm) so a merge is never one careless
 * click (anti-pattern #4: human-in-the-loop, never auto-merge).
 */
export function DuplicatesModal({ leadId, masterName, onClose, onSuccess }: Props) {
  const { data: candidates, isLoading, isError } = useLeadDuplicates(leadId, true);
  const merge = useMergeLeads(leadId);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleMerge() {
    if (selected.size === 0 || merge.isPending) return;
    setError(null);
    merge.mutate([...selected], {
      onSuccess: () => {
        onSuccess(selected.size);
        onClose();
      },
      onError: (err) => {
        if (err instanceof ApiError) {
          const detail = err.body as { detail?: string } | undefined;
          setError(detail?.detail ?? `Ошибка ${err.status}`);
        } else {
          setError("Не удалось объединить лиды");
        }
        setConfirming(false);
      },
    });
  }

  return (
    <Modal open onClose={onClose} title="Найти дубли" size="max-w-lg" dismissOnBackdrop={false}>
      <div className="-m-6 p-6 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-base font-bold tracking-tight text-ink">Найти дубли</h2>
            <p className="text-xs text-muted-2 mt-0.5">
              Похожие лиды по домену почты, телефону или компании. Выбранные
              объединятся в текущий — он станет основным.
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

        {/* Master row */}
        <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-xl bg-brand-soft/50 border border-brand-accent/15">
          <Crown size={14} className="text-brand-accent shrink-0" />
          <span className="text-sm font-semibold text-ink truncate">{masterName}</span>
          <span className="ml-auto shrink-0 text-2xs font-mono uppercase tracking-[0.12em] text-brand-accent-text">
            основной
          </span>
        </div>

        {/* Candidates */}
        {isLoading && (
          <div className="flex items-center justify-center py-10">
            <Loader2 size={20} className="animate-spin text-brand-muted" />
          </div>
        )}

        {isError && (
          <div className="flex items-start gap-2 bg-rose/5 border border-rose/20 rounded-xl px-3 py-2">
            <AlertTriangle size={14} className="text-rose shrink-0 mt-0.5" />
            <p className="text-xs text-rose">Не удалось загрузить кандидатов.</p>
          </div>
        )}

        {!isLoading && !isError && (candidates?.length ?? 0) === 0 && (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-brand-bg">
              <Users size={18} className="text-brand-muted" />
            </div>
            <p className="type-caption text-brand-muted">
              Дубликаты не найдены.
            </p>
          </div>
        )}

        {!isLoading && !isError && (candidates?.length ?? 0) > 0 && (
          <ul className="flex flex-col gap-1.5">
            {candidates!.map((c) => (
              <CandidateRow
                key={c.id}
                lead={c}
                checked={selected.has(c.id)}
                onToggle={() => toggle(c.id)}
              />
            ))}
          </ul>
        )}

        {/* Error */}
        {error && (
          <div className="mt-3 flex items-start gap-2 bg-rose/5 border border-rose/20 rounded-xl px-3 py-2">
            <AlertTriangle size={14} className="text-rose shrink-0 mt-0.5" />
            <p className="text-xs text-rose">{error}</p>
          </div>
        )}

        {/* Confirm panel */}
        {confirming && selected.size > 0 && (
          <div className="mt-4 flex items-start gap-2 bg-warning/5 border border-warning/20 rounded-xl px-3 py-2.5">
            <AlertTriangle size={14} className="text-warning shrink-0 mt-0.5" />
            <p className="text-xs text-brand-primary">
              {selected.size === 1
                ? "1 лид будет объединён"
                : `${selected.size} лида(ов) будут объединены`}{" "}
              в «{masterName}». Дубликаты архивируются (обратимо), их история и
              контакты переедут в основной лид.
            </p>
          </div>
        )}

        {/* Actions */}
        {!isLoading && !isError && (candidates?.length ?? 0) > 0 && (
          <div className="mt-4 flex gap-2 justify-end">
            <button
              type="button"
              onClick={confirming ? () => setConfirming(false) : onClose}
              className="px-4 py-2 rounded-pill text-sm font-semibold text-muted bg-canvas hover:bg-canvas-2 transition-all"
            >
              {confirming ? "Назад" : "Отмена"}
            </button>
            <button
              type="button"
              onClick={confirming ? handleMerge : () => setConfirming(true)}
              disabled={selected.size === 0 || merge.isPending}
              className="inline-flex items-center gap-1.5 px-5 py-2 rounded-pill text-sm font-semibold bg-ink text-white transition-all hover:bg-ink/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {merge.isPending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <CheckCircle2 size={13} />
              )}
              {confirming
                ? "Объединить"
                : selected.size > 0
                  ? `Объединить (${selected.size})`
                  : "Объединить"}
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}

function CandidateRow({
  lead,
  checked,
  onToggle,
}: {
  lead: LeadOut;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <li>
      <label
        className={`flex items-start gap-3 px-3 py-2.5 rounded-xl border cursor-pointer transition-colors ${
          checked
            ? "border-brand-accent/40 bg-brand-soft/40"
            : "border-brand-border hover:bg-canvas"
        }`}
      >
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          className="mt-0.5 h-4 w-4 shrink-0 accent-brand-accent"
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink truncate">{lead.company_name}</p>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 type-caption text-brand-muted">
            {lead.email && (
              <span className="inline-flex items-center gap-1 min-w-0">
                <Mail size={11} className="shrink-0" />
                <span className="truncate">{lead.email}</span>
              </span>
            )}
            {lead.phone && (
              <span className="inline-flex items-center gap-1">
                <Phone size={11} className="shrink-0" />
                {lead.phone}
              </span>
            )}
            {lead.city && (
              <span className="inline-flex items-center gap-1">
                <MapPin size={11} className="shrink-0" />
                {lead.city}
              </span>
            )}
          </div>
        </div>
      </label>
    </li>
  );
}
