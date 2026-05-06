"use client";
import { useState, useEffect, useRef } from "react";
import { X, Loader2 } from "lucide-react";
import { usePipelineStore } from "@/lib/store/pipeline-store";
import { useCreateLead } from "@/lib/hooks/use-leads";

export function CreateLeadModal() {
  const { createLeadModalOpen, closeCreateLeadModal } = usePipelineStore();
  const createLead = useCreateLead();
  const [companyName, setCompanyName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (createLeadModalOpen) {
      setCompanyName("");
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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const name = companyName.trim();
    if (!name) {
      setError("Введите название компании");
      return;
    }
    createLead.mutate(
      { company_name: name },
      {
        onSuccess: () => {
          closeCreateLeadModal();
        },
        onError: () => {
          setError("Ошибка при создании лида. Попробуйте ещё раз.");
        },
      }
    );
  }

  if (!createLeadModalOpen) return null;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-40 backdrop-blur-sm"
        onClick={closeCreateLeadModal}
      />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-sm p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-extrabold tracking-tight">Новый лид</h2>
            <button
              onClick={closeCreateLeadModal}
              className="text-muted hover:text-ink transition-colors p-1 rounded-lg hover:bg-black/5"
            >
              <X size={18} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-2 block mb-1.5">
                Компания *
              </label>
              <input
                ref={inputRef}
                type="text"
                value={companyName}
                onChange={(e) => {
                  setCompanyName(e.target.value);
                  setError(null);
                }}
                placeholder="ООО «Пример»"
                className="w-full px-4 py-2.5 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-accent/40 focus:bg-white transition-all duration-200"
              />
              {error && (
                <p className="text-xs text-rose mt-1">{error}</p>
              )}
            </div>

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
                disabled={createLead.isPending}
                className="inline-flex items-center gap-2 px-5 py-2 rounded-pill text-sm font-semibold bg-ink text-white transition-all hover:bg-ink/90 disabled:opacity-50"
              >
                {createLead.isPending && (
                  <Loader2 size={14} className="animate-spin" />
                )}
                Создать
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
