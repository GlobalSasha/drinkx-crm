"use client";
import { useState } from "react";
import { GitMerge, AlertTriangle, Loader2 } from "lucide-react";
import { useCompanyAutocomplete } from "@/lib/hooks/use-search";
import { useMergeCompanies } from "@/lib/hooks/use-companies";
import { ApiError } from "@/lib/api-client";
import { C } from "@/lib/design-system";

interface Props {
  sourceId: string;
  sourceName: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function CompanyMergeModal({ sourceId, sourceName, onClose, onSuccess }: Props) {
  const [query, setQuery] = useState("");
  const [targetId, setTargetId] = useState<string | null>(null);
  const [targetName, setTargetName] = useState<string>("");
  const [innConflict, setInnConflict] = useState<{ source: string; target: string } | null>(null);
  const { items, isFetching } = useCompanyAutocomplete(query);
  const merge = useMergeCompanies();

  function selectTarget(id: string, name: string) {
    if (id === sourceId) return;
    setTargetId(id);
    setTargetName(name);
    setQuery(name);
    setInnConflict(null);
  }

  function handleMerge(force = false) {
    if (!targetId) return;
    merge.mutate(
      { sourceId, targetId, force },
      {
        onSuccess: () => {
          onSuccess();
          onClose();
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 409) {
            const detail = (err.body as { detail?: Record<string, string> })?.detail;
            if (detail?.code === "inn_conflict") {
              setInnConflict({
                source: detail.source_inn ?? "—",
                target: detail.target_inn ?? "—",
              });
            }
          }
        },
      },
    );
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-soft">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-full bg-brand-panel">
            <GitMerge size={18} className="text-brand-accent-text" />
          </div>
          <div>
            <h2 className={`${C.cardTitle} font-bold ${C.color.text}`}>
              Объединить компании
            </h2>
            <p className={`${C.bodyXs} ${C.color.muted} mt-0.5`}>
              «{sourceName}» будет архивирована, её лиды и контакты перейдут к выбранной компании.
            </p>
          </div>
        </div>

        <div className="mb-4">
          <label className={`font-mono ${C.bodyXs} uppercase tracking-wider ${C.color.muted} block mb-1.5`}>
            Целевая компания
          </label>
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setTargetId(null);
            }}
            placeholder="Начните печатать название…"
            className={`w-full px-3 py-2 ${C.bodySm} bg-white border border-brand-border rounded-xl outline-none focus:border-brand-accent transition-colors`}
            autoFocus
          />
          {query && !targetId && items.length > 0 && (
            <ul className="mt-2 border border-brand-border rounded-2xl overflow-hidden max-h-60 overflow-y-auto">
              {items
                .filter((it) => it.id !== sourceId)
                .slice(0, 10)
                .map((it) => (
                  <li key={it.id}>
                    <button
                      type="button"
                      onClick={() => selectTarget(it.id, it.title)}
                      className={`flex flex-col w-full px-3 py-2 text-left hover:bg-brand-panel transition-colors`}
                    >
                      <span className={`${C.bodySm} font-semibold ${C.color.text}`}>{it.title}</span>
                      {it.subtitle && (
                        <span className={`${C.bodyXs} ${C.color.muted}`}>{it.subtitle}</span>
                      )}
                    </button>
                  </li>
                ))}
            </ul>
          )}
          {query && !isFetching && items.filter((it) => it.id !== sourceId).length === 0 && (
            <p className={`${C.bodyXs} ${C.color.muted} mt-2 italic`}>Совпадений нет.</p>
          )}
        </div>

        {innConflict && (
          <div className="flex items-start gap-2 bg-warning/5 border border-warning/30 rounded-2xl px-3 py-2.5 mb-4">
            <AlertTriangle size={14} className="text-warning shrink-0 mt-0.5" />
            <div className={`${C.bodyXs}`}>
              <p className="font-semibold text-warning">Разные ИНН</p>
              <p className={C.color.muted}>
                Исходный: {innConflict.source} · Целевой: {innConflict.target}.
                Объединить можно только с force-флагом.
              </p>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={merge.isPending}
            className={`px-4 py-1.5 ${C.btnLg} font-semibold ${C.button.ghost}`}
          >
            Отмена
          </button>
          {innConflict ? (
            <button
              type="button"
              onClick={() => handleMerge(true)}
              disabled={merge.isPending}
              className={`px-4 py-1.5 ${C.btnLg} font-semibold bg-warning text-white rounded-full disabled:opacity-50`}
            >
              {merge.isPending ? <Loader2 size={13} className="animate-spin" /> : "Объединить всё равно"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => handleMerge(false)}
              disabled={!targetId || merge.isPending}
              className={`px-4 py-1.5 ${C.btnLg} font-semibold bg-brand-accent text-white rounded-full disabled:opacity-40 disabled:cursor-not-allowed`}
            >
              {merge.isPending ? <Loader2 size={13} className="animate-spin" /> : `Объединить → ${targetName.slice(0, 20)}`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
