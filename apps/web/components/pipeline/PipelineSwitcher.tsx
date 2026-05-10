"use client";
// Pipeline switcher dropdown — Sprint 2.3 G2.
//
// Renders to the left of the action buttons in the /pipeline header.
// Single-pipeline workspaces see just the name (no chevron, not
// clickable) — there's nothing to switch to. Multi-pipeline workspaces
// get a chevroned button + popup with «по умолчанию» tagging on the
// workspace default + a separator + «Управление воронками →» link to
// /settings (the Settings panel lands in G3).
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronDown, Settings } from "lucide-react";
import { useMe } from "@/lib/hooks/use-me";
import { usePipelines } from "@/lib/hooks/use-pipelines";
import { usePipelineStore } from "@/lib/store/pipeline-store";

export function PipelineSwitcher() {
  const router = useRouter();
  const meQuery = useMe();
  const pipelinesQuery = usePipelines();

  const selectedPipelineId = usePipelineStore((s) => s.selectedPipelineId);
  const setSelectedPipeline = usePipelineStore((s) => s.setSelectedPipeline);
  const hydrate = usePipelineStore((s) => s.hydrateSelectedPipeline);

  const workspaceId = meQuery.data?.workspace.id;
  const defaultPipelineId =
    meQuery.data?.workspace.default_pipeline_id ?? null;
  const pipelines = pipelinesQuery.data ?? [];

  // Hydrate the store once both /me and /pipelines have resolved.
  // The store keys persistence by workspace_id so a user who belongs
  // to two workspaces never gets a leaked selection across the
  // boundary (risk #2 in 04_NEXT_SPRINT.md).
  useEffect(() => {
    if (!workspaceId || pipelines.length === 0) return;
    hydrate(
      workspaceId,
      pipelines.map((p) => p.id),
      defaultPipelineId,
    );
  }, [workspaceId, defaultPipelineId, pipelines, hydrate]);

  // Outside-click to close
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  // Loading + empty states — render nothing rather than a flicker
  // shell so the header doesn't reflow when /pipelines comes back.
  if (pipelinesQuery.isLoading || pipelines.length === 0) {
    return null;
  }

  const selectedPipeline =
    pipelines.find((p) => p.id === selectedPipelineId) ??
    pipelines.find((p) => p.id === defaultPipelineId) ??
    pipelines[0];

  // Single-pipeline workspaces — show the name in a non-interactive
  // chip. No chevron, no popup, no «Управление» link (admin can still
  // reach Settings via the sidebar). Avoids implying the user can
  // switch when there's nothing to switch to.
  if (pipelines.length === 1) {
    return (
      <span className="inline-flex items-center gap-1.5 bg-canvas border border-black/10 rounded-pill px-3 py-1.5 text-sm font-semibold text-ink">
        {selectedPipeline.name}
      </span>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 bg-canvas text-ink border border-black/10 rounded-pill px-3 py-1.5 text-sm font-semibold transition-all duration-300 hover:bg-canvas-2 hover:border-black/20 active:scale-[0.98]"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate max-w-[180px]">{selectedPipeline.name}</span>
        <ChevronDown
          size={14}
          className={`transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute left-0 top-full mt-1 z-30 min-w-[260px] bg-white border border-black/10 rounded-xl shadow-soft py-1 overflow-hidden"
        >
          {pipelines.map((p) => {
            const isSelected = p.id === selectedPipeline.id;
            const isDefault = p.id === defaultPipelineId;
            return (
              <button
                key={p.id}
                type="button"
                role="option"
                aria-selected={isSelected}
                onClick={() => {
                  if (workspaceId) {
                    setSelectedPipeline(workspaceId, p.id);
                  }
                  setOpen(false);
                }}
                className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors ${
                  isSelected
                    ? "bg-canvas/60 text-ink"
                    : "text-ink hover:bg-canvas/60"
                }`}
              >
                <Check
                  size={14}
                  className={`shrink-0 ${
                    isSelected ? "text-brand-accent" : "opacity-0"
                  }`}
                />
                <span className="flex-1 min-w-0 truncate font-semibold">
                  {p.name}
                </span>
                {isDefault && (
                  <span className="text-[10px] font-mono uppercase tracking-wide text-muted-3 shrink-0">
                    по умолчанию
                  </span>
                )}
              </button>
            );
          })}

          <div className="border-t border-black/5 my-1" />

          <button
            type="button"
            onClick={() => {
              setOpen(false);
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              router.push("/settings" as any);
            }}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-muted hover:text-ink hover:bg-canvas/60 transition-colors"
          >
            <Settings size={14} className="shrink-0" />
            <span className="flex-1 text-left">Управление воронками →</span>
          </button>
        </div>
      )}
    </div>
  );
}
