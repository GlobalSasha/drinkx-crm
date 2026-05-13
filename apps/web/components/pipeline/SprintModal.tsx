"use client";
import { useState, useEffect, useCallback } from "react";
import { X, Loader2 } from "lucide-react";
import { usePipelineStore } from "@/lib/store/pipeline-store";
import { usePoolLeads, useCreateSprint } from "@/lib/hooks/use-leads";
import { Toast } from "@/components/ui/Toast";
import { SEGMENT_CHOICES } from "@/lib/constants/segments";

const SPRINT_CAPACITY = 20; // fallback if workspace value unavailable

interface ToastState {
  id: number;
  message: string;
  type: "error" | "success";
}

interface Props {
  /** When provided, component is used standalone (not driven by pipeline store). */
  isOpen?: boolean;
  onClose?: () => void;
}

export function SprintModal({ isOpen: isOpenProp, onClose: onCloseProp }: Props = {}) {
  // Standalone mode: props override; pipeline mode: read from store.
  const { sprintModalOpen, closeSprintModal } = usePipelineStore();
  const isOpen = isOpenProp !== undefined ? isOpenProp : sprintModalOpen;
  const closeModal = onCloseProp ?? closeSprintModal;

  const [selectedCities, setSelectedCities] = useState<string[]>([]);
  const [selectedSegment, setSelectedSegment] = useState<string | null>(null);
  const [toasts, setToasts] = useState<ToastState[]>([]);

  const addToast = useCallback(
    (message: string, type: "error" | "success" = "success") => {
      const id = Date.now();
      setToasts((prev) => [...prev, { id, message, type }]);
      setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
    },
    []
  );

  // Close on Esc
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeModal();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, closeModal]);

  const poolQuery = usePoolLeads({
    segment: selectedSegment ?? undefined,
  });

  const createSprint = useCreateSprint();

  // Unique cities in pool
  const poolCities = Array.from(
    new Set(
      (poolQuery.data?.items ?? [])
        .map((l) => l.city)
        .filter(Boolean) as string[]
    )
  ).sort();

  // Filter pool by selected cities for preview count
  const filteredPool = (poolQuery.data?.items ?? []).filter((l) => {
    if (selectedCities.length > 0 && (!l.city || !selectedCities.includes(l.city)))
      return false;
    return true;
  });
  const previewFound = filteredPool.length;
  const previewAdded = Math.min(previewFound, SPRINT_CAPACITY);

  function toggleCity(city: string) {
    setSelectedCities((prev) =>
      prev.includes(city) ? prev.filter((c) => c !== city) : [...prev, city]
    );
  }

  function handleSubmit() {
    createSprint.mutate(
      {
        cities: selectedCities,
        segment: selectedSegment,
        limit: SPRINT_CAPACITY,
      },
      {
        onSuccess: (data) => {
          addToast(`Добавлено ${data.claimed_count} карточек в ваш спринт`, "success");
          setSelectedCities([]);
          setSelectedSegment(null);
          setTimeout(closeModal, 1500);
        },
        onError: () => {
          addToast("Ошибка при формировании спринта", "error");
        },
      }
    );
  }

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40 backdrop-blur-sm"
        onClick={closeModal}
      />

      {/* Dialog */}
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-md p-6 relative">
          {/* Header */}
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-lg font-bold tracking-tight">
              Новый спринт
            </h2>
            <button
              onClick={closeModal}
              className="text-muted hover:text-ink transition-colors p-1 rounded-lg hover:bg-black/5"
            >
              <X size={18} />
            </button>
          </div>

          {/* Segment selector */}
          <div className="mb-5">
            <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-2 block mb-2">
              Сегмент
            </label>
            <div className="flex flex-wrap gap-1.5">
              <SegmentChip
                active={selectedSegment === null}
                onClick={() => setSelectedSegment(null)}
              >
                Все
              </SegmentChip>
              {SEGMENT_CHOICES.map((s) => (
                <SegmentChip
                  key={s.key}
                  active={selectedSegment === s.key}
                  onClick={() =>
                    setSelectedSegment(selectedSegment === s.key ? null : s.key)
                  }
                >
                  {s.label}
                </SegmentChip>
              ))}
            </div>
          </div>

          {/* City multi-select */}
          <div className="mb-5">
            <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-2 block mb-2">
              Города
              {poolQuery.isLoading && (
                <Loader2 size={10} className="inline-block ml-1 animate-spin" />
              )}
            </label>
            {poolCities.length === 0 && !poolQuery.isLoading ? (
              <p className="text-xs text-muted-2">Нет доступных городов в пуле</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {poolCities.map((city) => (
                  <button
                    key={city}
                    onClick={() => toggleCity(city)}
                    className={`px-3 py-1.5 rounded-pill text-xs font-semibold border transition-all duration-200 ${
                      selectedCities.includes(city)
                        ? "bg-brand-accent text-white border-brand-accent"
                        : "bg-canvas border-black/10 text-muted hover:border-brand-accent/40"
                    }`}
                  >
                    {city}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Preview */}
          <div className="bg-canvas rounded-xl px-4 py-3 mb-5">
            <p className="text-sm text-muted">
              Найдено{" "}
              <span className="font-semibold text-ink">{previewFound}</span>{" "}
              карточек → добавится{" "}
              <span className="font-semibold text-brand-accent">{previewAdded}</span>
            </p>
          </div>

          {/* Actions */}
          <div className="flex gap-2 justify-end">
            <button
              onClick={closeModal}
              className="px-4 py-2 rounded-pill text-sm font-semibold text-muted bg-canvas hover:bg-canvas-2 transition-all duration-200"
            >
              Отмена
            </button>
            <button
              onClick={handleSubmit}
              disabled={createSprint.isPending || previewAdded === 0}
              className="inline-flex items-center gap-2 px-5 py-2 rounded-pill text-sm font-semibold bg-brand-accent text-white transition-all duration-200 hover:bg-brand-accent/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {createSprint.isPending && (
                <Loader2 size={14} className="animate-spin" />
              )}
              Сформировать
            </button>
          </div>
        </div>
      </div>

      {/* Toasts */}
      <div className="fixed bottom-6 right-6 flex flex-col gap-2 z-[60] pointer-events-none">
        {toasts.map((t) => (
          <Toast key={t.id} message={t.message} type={t.type} />
        ))}
      </div>
    </>
  );
}

function SegmentChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-pill text-xs font-semibold transition-all duration-200 ${
        active
          ? "bg-ink text-white"
          : "bg-canvas text-muted hover:bg-canvas-2"
      }`}
    >
      {children}
    </button>
  );
}
