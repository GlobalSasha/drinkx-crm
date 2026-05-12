"use client";
import { useState, useEffect, useRef } from "react";
import { X, Loader2, Plus, Sparkles } from "lucide-react";
import { usePipelineStore } from "@/lib/store/pipeline-store";
import { useCreateLead } from "@/lib/hooks/use-leads";
import { useCompanyAutocomplete } from "@/lib/hooks/use-search";
import { useCreateCompany } from "@/lib/hooks/use-companies";
import { ApiError } from "@/lib/api-client";
import type { DuplicateWarningResponse, SearchHit } from "@/lib/types";

/** Sprint 3.3 — autocomplete-first. Manager picks an existing company
 *  (lead.company_id set, name copied server-side) or creates a new one
 *  via «Создать новую: …». New-company flow goes through the
 *  duplicate-warning protocol: first POST without force → 409 surfaces
 *  candidates → manager picks one or re-POSTs with force. */
export function CreateLeadModal() {
  const { createLeadModalOpen, closeCreateLeadModal } = usePipelineStore();
  const createLead = useCreateLead();
  const createCompany = useCreateCompany();
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<SearchHit | null>(null);
  const [duplicateCandidates, setDuplicateCandidates] = useState<
    DuplicateWarningResponse["candidates"] | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { items: companyHits, isFetching } = useCompanyAutocomplete(query);

  useEffect(() => {
    if (createLeadModalOpen) {
      setQuery("");
      setPicked(null);
      setDuplicateCandidates(null);
      setError(null);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [createLeadModalOpen]);

  // Close on Esc
  useEffect(() => {
    if (!createLeadModalOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeCreateLeadModal();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [createLeadModalOpen, closeCreateLeadModal]);

  function pickExisting(hit: SearchHit) {
    setPicked(hit);
    setQuery(hit.title);
    setDuplicateCandidates(null);
    setError(null);
  }

  function createWithExisting(companyId: string) {
    createLead.mutate(
      { company_name: "", company_id: companyId } as Parameters<typeof createLead.mutate>[0],
      {
        onSuccess: () => closeCreateLeadModal(),
        onError: () => setError("Не удалось создать лид"),
      },
    );
  }

  function createNewCompanyThenLead(name: string, force: boolean) {
    createCompany.mutate(
      { payload: { name }, force },
      {
        onSuccess: (company) => createWithExisting(company.id),
        onError: (err) => {
          if (err instanceof ApiError && err.status === 409) {
            const detail = err.body as { detail?: DuplicateWarningResponse };
            const inner = detail?.detail;
            if (inner?.error === "duplicate_warning") {
              setDuplicateCandidates(inner.candidates);
              return;
            }
          }
          setError("Не удалось создать компанию");
        },
      },
    );
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const name = query.trim();
    if (!name) {
      setError("Введите название компании");
      return;
    }
    if (picked) {
      createWithExisting(picked.id);
      return;
    }
    createNewCompanyThenLead(name, false);
  }

  if (!createLeadModalOpen) return null;

  const showCreateNewItem = query.trim().length > 0 && !picked;
  const pending = createLead.isPending || createCompany.isPending;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-40 backdrop-blur-sm"
        onClick={closeCreateLeadModal}
      />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-md p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold tracking-tight">Новый лид</h2>
            <button
              onClick={closeCreateLeadModal}
              className="text-muted hover:text-ink transition-colors p-1 rounded-lg hover:bg-black/5"
            >
              <X size={18} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-2 block mb-1.5">
                Компания *
              </label>
              <div className="relative">
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setPicked(null);
                    setDuplicateCandidates(null);
                    setError(null);
                  }}
                  placeholder="Начните печатать название…"
                  className="w-full px-4 py-2.5 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 focus:bg-white transition-all duration-200"
                />
                {isFetching && (
                  <Loader2
                    size={14}
                    className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-muted"
                  />
                )}
              </div>

              {!picked && query.trim().length > 0 && (
                <ul className="mt-2 border border-black/10 rounded-2xl overflow-hidden max-h-60 overflow-y-auto bg-white">
                  {companyHits.slice(0, 8).map((it) => (
                    <li key={it.id}>
                      <button
                        type="button"
                        onClick={() => pickExisting(it)}
                        className="flex flex-col w-full px-3 py-2 text-left hover:bg-canvas transition-colors"
                      >
                        <span className="text-sm font-semibold text-ink truncate">
                          {it.title}
                        </span>
                        {it.subtitle && (
                          <span className="text-xs text-muted truncate">{it.subtitle}</span>
                        )}
                      </button>
                    </li>
                  ))}
                  {showCreateNewItem && (
                    <li className="border-t border-black/5">
                      <button
                        type="submit"
                        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-canvas transition-colors"
                      >
                        <Plus size={13} className="text-brand-accent" />
                        <span className="text-sm font-semibold text-brand-accent-text">
                          Создать новую: {query.trim()}
                        </span>
                      </button>
                    </li>
                  )}
                </ul>
              )}

              {picked && (
                <div className="mt-2 flex items-center gap-2 px-3 py-2 rounded-2xl bg-brand-bg">
                  <Sparkles size={13} className="text-brand-accent shrink-0" />
                  <span className="text-sm font-semibold text-brand-accent-text">
                    Использовать «{picked.title}»
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setPicked(null);
                      setTimeout(() => inputRef.current?.focus(), 0);
                    }}
                    className="ml-auto text-xs text-muted hover:text-ink"
                  >
                    Сбросить
                  </button>
                </div>
              )}
            </div>

            {duplicateCandidates && duplicateCandidates.length > 0 && (
              <div className="rounded-2xl bg-warning/5 border border-warning/30 p-3">
                <p className="text-xs font-semibold text-warning mb-2">
                  Похожая компания уже существует:
                </p>
                <ul className="space-y-1.5 mb-3">
                  {duplicateCandidates.slice(0, 3).map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => createWithExisting(c.id)}
                        className="flex items-baseline justify-between w-full px-2 py-1.5 rounded-xl hover:bg-white transition-colors text-left"
                      >
                        <span className="text-sm font-semibold text-ink truncate">
                          {c.name}
                        </span>
                        <span className="text-xs text-muted shrink-0 ml-2 font-mono">
                          {c.leads_count} сделок
                          {c.inn && ` · ИНН ${c.inn}`}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={() => createNewCompanyThenLead(query.trim(), true)}
                  className="text-xs font-semibold text-rose hover:underline"
                >
                  Всё равно создать новую
                </button>
              </div>
            )}

            {error && <p className="text-xs text-rose">{error}</p>}

            <div className="flex gap-2 justify-end pt-1">
              <button
                type="button"
                onClick={closeCreateLeadModal}
                className="px-4 py-2 rounded-pill text-sm font-semibold text-muted bg-canvas hover:bg-canvas-2 transition-all"
              >
                Отмена
              </button>
              <button
                type="submit"
                disabled={pending || query.trim().length === 0}
                className="inline-flex items-center gap-2 px-5 py-2 rounded-pill text-sm font-semibold bg-ink text-white transition-all hover:bg-ink/90 disabled:opacity-50"
              >
                {pending && <Loader2 size={14} className="animate-spin" />}
                {picked ? "Создать лид" : "Создать"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
