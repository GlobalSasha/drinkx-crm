"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { PipelineHeader } from "@/components/pipeline/PipelineHeader";
import { PipelineBoard } from "@/components/pipeline/PipelineBoard";
import { PipelineList } from "@/components/pipeline/PipelineList";
import { SprintModal } from "@/components/pipeline/SprintModal";
import { CreateLeadModal } from "@/components/pipeline/CreateLeadModal";
import { usePipelines } from "@/lib/hooks/use-pipelines";
import { useLeads } from "@/lib/hooks/use-leads";
import { useMe } from "@/lib/hooks/use-me";
import { useUsers } from "@/lib/hooks/use-users";
import { usePipelineStore } from "@/lib/store/pipeline-store";

export default function PipelinePage() {
  // `useSearchParams` (deep-link `?stage=…` / `?filter=…` reader)
  // requires a Suspense boundary to keep the page out of the static
  // rendering bail-out path during `next build`.
  return (
    <Suspense fallback={null}>
      <PipelinePageInner />
    </Suspense>
  );
}

function PipelinePageInner() {
  const { filters, selectedPipelineId } = usePipelineStore();
  const searchParams = useSearchParams();
  const stageParam = searchParams.get("stage");
  // `filter` is read for forward compatibility (link sources expect
  // values like `rotting` / `followup_overdue`) but currently has no
  // matching action in usePipelineStore — applying it would require
  // adding new store fields, which is out of scope for this change.
  const filterParam = searchParams.get("filter");
  const meQuery = useMe();
  const pipelinesQuery = usePipelines();

  // Manager workload: admin/head can scope the board to «Мои» (self —
  // default, empty string), a specific manager (their user id), or «Все»
  // (the whole workspace, `all`). Regular users never see the control.
  const isPrivileged =
    meQuery.data?.role === "admin" || meQuery.data?.role === "head";
  const usersQuery = useUsers();

  // Deep-link from /team workload table: /pipeline?assigned_to=<id>.
  // `useSearchParams()` is synchronous on the client, so we seed the
  // scope directly from the URL — no extra leads fetch on cold load.
  // Holding a user id while not privileged is harmless: the
  // `isPrivileged &&` guards on the `useLeads` params suppress it.
  const assignedParam = searchParams.get("assigned_to") ?? "";
  const [ownerScope, setOwnerScope] = useState<string>(assignedParam);

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

  // Server-side: pipeline + free-text search only. Segment/city
  // multi-select are applied client-side below — keeps the dropdowns
  // independent of the API's single-value query params.
  const leadsQuery = useLeads({
    pipeline_id: activePipelineId ?? undefined,
    q: filters.q || undefined,
    assigned_to:
      isPrivileged && ownerScope && ownerScope !== "all"
        ? ownerScope
        : undefined,
    all_assignees: isPrivileged && ownerScope === "all" ? true : undefined,
    page_size: 200,
  });

  const rawLeads = leadsQuery.data?.items ?? [];

  const allLeads = useMemo(() => {
    const segSet = new Set(filters.segments);
    const citySet = new Set(filters.cities);
    return rawLeads.filter((l) => {
      if (segSet.size > 0 && (!l.segment || !segSet.has(l.segment))) return false;
      if (citySet.size > 0 && (!l.city || !citySet.has(l.city))) return false;
      return true;
    });
  }, [rawLeads, filters.segments, filters.cities]);

  const isLoading =
    meQuery.isLoading || pipelinesQuery.isLoading || leadsQuery.isLoading;
  const isError =
    meQuery.isError || pipelinesQuery.isError || leadsQuery.isError;

  // Deep-link support for `/pipeline?stage={id}`. The columns mount
  // their own `id="stage-col-{id}"` so we look it up after the data
  // resolves and bring it into view.
  useEffect(() => {
    if (isLoading || isError || !stageParam) return;
    const el = document.getElementById(`stage-col-${stageParam}`);
    el?.scrollIntoView({
      behavior: "smooth",
      block: "start",
      inline: "start",
    });
    // `filterParam` has no matching action in usePipelineStore yet —
    // intentionally a no-op so the param can be read once the store
    // gains a quick-filter field. Referencing it keeps the dep array
    // honest if that wiring lands without touching this effect.
    void filterParam;
  }, [isLoading, isError, stageParam, filterParam]);

  return (
    <div className="flex flex-col h-screen bg-brand-bg overflow-hidden">
      {/* Header derives filter options + per-option counts from the
          unfiltered set so selecting one segment doesn't hide the rest.
          Total badge reflects the visible (post-filter) count. */}
      <PipelineHeader
        leads={rawLeads}
        totalCount={allLeads.length}
      />

      {/* Owner scope — admin/head only. «Мои» = self (default), «Все» =
          whole workspace, otherwise a specific manager's leads. Deep-linked
          to from the /team workload table via ?assigned_to=<id>. */}
      {!meQuery.isLoading && isPrivileged && (
        <div className="flex items-center gap-2 px-4 sm:px-6 py-2 bg-white border-b border-brand-border">
          <label htmlFor="owner-scope" className="text-brand-muted text-xs">
            Ответственный
          </label>
          <select
            id="owner-scope"
            value={ownerScope}
            onChange={(e) => setOwnerScope(e.target.value)}
            className="h-8 px-3 text-sm bg-brand-bg border border-brand-border rounded-full outline-none focus:border-brand-accent/40 focus:bg-white transition duration-300"
          >
            <option value="">Мои</option>
            <option value="all">Все</option>
            {(usersQuery.data?.items ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.name || u.email}
              </option>
            ))}
          </select>
        </div>
      )}

      {isLoading && (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 size={24} className="animate-spin text-brand-muted" />
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
      <CreateLeadModal />
      {/* ImportWizard is mounted globally in (app)/layout.tsx so any
          page can open it via pipeline-store.openImportWizard(). */}
    </div>
  );
}
