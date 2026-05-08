"use client";
import { Loader2 } from "lucide-react";
import { PipelineHeader } from "@/components/pipeline/PipelineHeader";
import { PipelineBoard } from "@/components/pipeline/PipelineBoard";
import { PipelineList } from "@/components/pipeline/PipelineList";
import { SprintModal } from "@/components/pipeline/SprintModal";
import { BriefDrawer } from "@/components/pipeline/BriefDrawer";
import { CreateLeadModal } from "@/components/pipeline/CreateLeadModal";
import { usePipelines } from "@/lib/hooks/use-pipelines";
import { useLeads } from "@/lib/hooks/use-leads";
import { useMe } from "@/lib/hooks/use-me";
import { usePipelineStore } from "@/lib/store/pipeline-store";

export default function PipelinePage() {
  const { filters, selectedPipelineId } = usePipelineStore();
  const meQuery = useMe();
  const pipelinesQuery = usePipelines();

  // Resolve which pipeline to render the board for. The switcher
  // hydrates `selectedPipelineId` on mount; before that lands we
  // fall back to the workspace default so the board doesn't flicker
  // through an empty intermediate state on cold-load.
  const pipelines = pipelinesQuery.data ?? [];
  const defaultPipelineId =
    meQuery.data?.workspace.default_pipeline_id ?? null;
  const activePipelineId =
    selectedPipelineId ??
    defaultPipelineId ??
    pipelines[0]?.id ??
    null;

  const activePipeline = pipelines.find((p) => p.id === activePipelineId);
  // Stages come straight from the resolved Pipeline.stages now —
  // Sprint 2.3 G1 returns them eagerly. Replaces the heuristic UUID-
  // patching the previous fallback path needed.
  const stages = activePipeline?.stages ?? [];

  const leadsQuery = useLeads({
    pipeline_id: activePipelineId ?? undefined,
    segment: filters.segment ?? undefined,
    city: filters.city ?? undefined,
    q: filters.q || undefined,
    page_size: 200,
  });

  const allLeads = leadsQuery.data?.items ?? [];

  const isLoading =
    meQuery.isLoading || pipelinesQuery.isLoading || leadsQuery.isLoading;
  const isError =
    meQuery.isError || pipelinesQuery.isError || leadsQuery.isError;

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
        <>
          {/* List view for narrow viewports — touch drag-drop is out of
              scope per PRD §8.6, so the Kanban is replaced by a flat
              read-only grouped list below md. */}
          <div className="md:hidden flex flex-col flex-1 min-h-0">
            <PipelineList stages={stages} leads={allLeads} />
          </div>
          {/* Kanban — md+ only */}
          <div className="hidden md:flex flex-col flex-1 min-h-0">
            <PipelineBoard stages={stages} leads={allLeads} />
          </div>
        </>
      )}

      <SprintModal />
      <BriefDrawer />
      <CreateLeadModal />
      {/* ImportWizard is mounted globally in (app)/layout.tsx so any
          page can open it via pipeline-store.openImportWizard(). */}
    </div>
  );
}
