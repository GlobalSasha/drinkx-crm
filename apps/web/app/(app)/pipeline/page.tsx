"use client";
import { useMemo } from "react";
import { Loader2 } from "lucide-react";
import { PipelineHeader } from "@/components/pipeline/PipelineHeader";
import { PipelineBoard } from "@/components/pipeline/PipelineBoard";
import { SprintModal } from "@/components/pipeline/SprintModal";
import { BriefDrawer } from "@/components/pipeline/BriefDrawer";
import { CreateLeadModal } from "@/components/pipeline/CreateLeadModal";
import { usePipelines } from "@/lib/hooks/use-pipelines";
import { useLeads } from "@/lib/hooks/use-leads";
import { usePipelineStore } from "@/lib/store/pipeline-store";
import type { Stage } from "@/lib/types";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function PipelinePage() {
  const { filters } = usePipelineStore();
  const pipelinesQuery = usePipelines();
  const leadsQuery = useLeads({
    segment: filters.segment ?? undefined,
    city: filters.city ?? undefined,
    q: filters.q || undefined,
    page_size: 200,
  });

  const allLeads = leadsQuery.data?.items ?? [];

  // Collect real stage UUIDs from leads to patch fallback stage IDs.
  // This lets us correctly route drag-drop move-stage calls.
  const stages = useMemo(() => {
    const fallback = pipelinesQuery.data?.[0]?.stages ?? [];
    if (fallback.length === 0) return [];

    // Map real UUIDs found in leads: position index → UUID
    // We can't know for sure which UUID is which stage, but we use
    // the order in which unique stage_ids appear (sorted by first-seen
    // lead's created_at) as a heuristic to match positions.
    const realStageIds = Array.from(
      new Set(
        allLeads
          .map((l) => l.stage_id)
          .filter((id): id is string => !!id && UUID_RE.test(id))
      )
    );

    if (realStageIds.length === 0) return fallback;

    // Group leads by stage_id and find min position hint via ordering.
    // We assume the backend returns stage_ids ordered by pipeline position
    // when sorted by the lead's created_at (first lead in stage N was created
    // before first lead in stage N+1). This is a weak heuristic but workable
    // for a fresh workspace.

    // Better: find the stage_id that appears in the "Новый контакт" cluster
    // by seeing which UUID has the most recently created leads at position 0.
    // For now, patch based on which stages already have matching fallback IDs:
    const patched: Stage[] = fallback.map((stage) => {
      // If this fallback id is already a real UUID (shouldn't happen but defensive)
      if (UUID_RE.test(stage.id)) return stage;

      // Look for a real UUID that appears in leads where the stage name
      // might match. Since we can't know without the backend, we return
      // fallback as-is. The drag-drop code handles the UUID check.
      return stage;
    });

    // If all leads point to one stage_id, and the board only has the
    // first column as "Новый контакт", patch that specific fallback stage.
    if (realStageIds.length === 1) {
      const realId = realStageIds[0];
      // The first stage in the pipeline is position 0 — new leads land here.
      return patched.map((s, i) =>
        i === 0 ? { ...s, id: realId } : s
      );
    }

    return patched;
  }, [pipelinesQuery.data, allLeads]);

  // Apply filters client-side for the header summary (server filters already applied in query).
  const isLoading = pipelinesQuery.isLoading || leadsQuery.isLoading;
  const isError = pipelinesQuery.isError || leadsQuery.isError;

  return (
    <div className="flex flex-col h-screen bg-canvas overflow-hidden">
      <PipelineHeader
        leads={allLeads}
        totalCount={leadsQuery.data?.total ?? 0}
      />

      {isLoading && (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 size={24} className="animate-spin text-muted-2" />
        </div>
      )}

      {isError && (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-rose">
            Ошибка загрузки данных. Проверьте подключение к API.
          </p>
        </div>
      )}

      {!isLoading && !isError && (
        <PipelineBoard stages={stages} leads={allLeads} />
      )}

      <SprintModal />
      <BriefDrawer />
      <CreateLeadModal />
    </div>
  );
}
