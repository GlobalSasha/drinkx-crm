"use client";
import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { Loader2, AlertTriangle } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { useLead, useUpdateLead } from "@/lib/hooks/use-lead";
import { usePipelines, DEFAULT_STAGES } from "@/lib/hooks/use-pipelines";
import { DEFAULT_GATE_CRITERIA } from "@/lib/types";
import { useClaimLead, useMoveStage, useUnclaimLead } from "@/lib/hooks/use-leads";
import { useMe } from "@/lib/hooks/use-me";
import type { Stage } from "@/lib/types";
import { ContactsTab } from "./ContactsTab";
import { QuoteTab } from "./QuoteTab";
import { TasksTab } from "./TasksTab";
import { NotesTab } from "./NotesTab";
import { ArchiveTab } from "./ArchiveTab";
import { UnifiedFeed } from "./feed/UnifiedFeed";
import { LeadLeftColumn } from "./LeadLeftColumn";
import { StagesStepper } from "./StagesStepper";
import { GateModal } from "./GateModal";
import { LostModal } from "./LostModal";
import { TransferModal } from "./TransferModal";
import { DuplicatesModal } from "./DuplicatesModal";
import { DeleteConfirmModal } from "./DeleteConfirmModal";
import { LeadCardHeader } from "./LeadCardHeader";
import { NextStepPrompt } from "./NextStepPrompt";
import { useFeed } from "@/lib/hooks/use-feed";
import { useLeaveGuard } from "@/lib/hooks/use-leave-guard";
import { C } from "@/lib/design-system";

// Lead Card v3 — two-pane: key info lives in the always-visible left column,
// the right column switches between these tabs. The old «Информация» tab is
// gone (its deal params moved to the left column).
type TabKey = "activity" | "tasks" | "contacts" | "quote" | "notes" | "archive";

const TABS: { key: TabKey; label: string }[] = [
  { key: "activity", label: "Активность" },
  { key: "tasks", label: "Задачи" },
  { key: "contacts", label: "Контакты" },
  { key: "quote", label: "КП" },
  { key: "notes", label: "Заметки" },
  { key: "archive", label: "Архив" },
];

interface Props {
  leadId: string;
}

export function LeadCard({ leadId }: Props) {
  const { data: lead, isLoading, isError } = useLead(leadId);
  const pipelinesQuery = usePipelines();
  const updateLead = useUpdateLead(leadId);
  const moveStage = useMoveStage();
  const unclaim = useUnclaimLead();
  const claim = useClaimLead();
  const me = useMe().data;
  const router = useRouter();
  const pathname = usePathname();

  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const initialTab: TabKey = TABS.some((t) => t.key === tabParam)
    ? (tabParam as TabKey)
    : "activity";
  const [activeTab, setActiveTab] = useState<TabKey>(initialTab);
  const [gateTarget, setGateTarget] = useState<Stage | null>(null);
  const [lostStage, setLostStage] = useState<Stage | null>(null);
  const [transferOpen, setTransferOpen] = useState(false);
  const [dupOpen, setDupOpen] = useState(false);
  // Lead Card v2: «Закрыто» button is now a tiny dropdown so the
  // manager picks Won / Lost without going through CloseModal's
  // grid. Won → straight call into useMoveStage; Lost → opens the
  // existing LostModal with the required reason field.
  const [deleteOpen, setDeleteOpen] = useState(false);
  // Header dropdowns («Закрыть сделку ▾» and «⋯») are now Radix-driven —
  // Esc handling and click-outside come for free from DropdownMenu.
  const [toast, setToast] = useState<string | null>(null);
  // Lead Card v3 — the composer (right column, Активность) is driven into
  // task mode by the left column's «Следующий шаг». State lives here so the
  // two columns can talk.
  const [composerModeRequest, setComposerModeRequest] = useState<
    "comment" | "task" | "call" | "file" | null
  >(null);

  // «← объединён из N» note — derived from the `system` audit Activity the
  // merge writes (payload_json.merged_lead_ids). Reuses the feed cache that
  // the Activity tab already populates (same query key), so no extra fetch.
  const feed = useFeed(leadId);
  const mergedFromCount = useMemo(() => {
    let n = 0;
    for (const page of feed.data?.pages ?? []) {
      for (const item of page.items) {
        const ids = item.payload_json?.merged_lead_ids;
        if (item.type === "system" && Array.isArray(ids)) n += ids.length;
      }
    }
    return n;
  }, [feed.data]);

  // Flatten the feed for the left column's «Следующий шаг» (NextStepBanner).
  // Same `useFeed` cache key as UnifiedFeed — no extra fetch.
  const items = useMemo(
    () => feed.data?.pages.flatMap((p) => p.items) ?? [],
    [feed.data],
  );

  const stages: Stage[] =
    pipelinesQuery.data?.[0]?.stages ??
    DEFAULT_STAGES.map((s, i) => ({
      ...s,
      id: `fallback-${i}`,
      pipeline_id: "default",
    }));

  const currentStage = stages.find((s) => s.id === lead?.stage_id);
  const displayStage = currentStage ?? stages[0];

  // Lead Card v3 — Phase 2: when the manager leaves a card that has no open
  // task (and isn't closed), prompt them to schedule the next step. The guard
  // intercepts in-app link clicks; the original href is held in `pendingHref`
  // until the manager saves a task or skips.
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const hasOpenTask = useMemo(
    () => items.some((it) => it.type === "task" && !it.task_done),
    [items],
  );
  const leadClosed = !!(currentStage?.is_won || currentStage?.is_lost);
  const handleIntercept = useCallback((href: string) => setPendingHref(href), []);
  useLeaveGuard(!!lead && !leadClosed && !hasOpenTask, pathname, handleIntercept);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  }

  function handleStageSelect(stage: Stage) {
    if (!lead) return;
    const hasCriteria =
      (stage.gate_criteria_json?.length ?? 0) > 0 || stage.position > 0;
    if (hasCriteria) {
      setGateTarget(stage);
    } else {
      moveStage.mutate({ leadId, body: { stage_id: stage.id } });
    }
  }

  function handleReturnToPool() {
    if (!lead || unclaim.isPending) return;
    unclaim.mutate(leadId, {
      onSuccess: () => router.push("/pipeline"),
    });
  }

  function handleClaim() {
    if (!lead || claim.isPending) return;
    claim.mutate(leadId, {
      onSuccess: () => showToast("Лид в работе"),
      onError: (err) => {
        const msg =
          err.status === 409
            ? "Эту карточку только что взял другой менеджер"
            : "Не удалось взять лид в работу";
        showToast(msg);
      },
    });
  }

  if (isLoading) {
    return (
      <div className="font-sans min-h-screen bg-brand-bg flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-brand-muted" />
      </div>
    );
  }

  if (isError || !lead) {
    return (
      <div className="font-sans min-h-screen bg-brand-bg flex flex-col items-center justify-center gap-4">
        <AlertTriangle size={24} className="text-rose" />
        <p className="type-caption text-rose">Лид не найден или ошибка загрузки</p>
        <Link href="/pipeline" className={`type-caption ${C.color.accent}`}>
          ← Назад к воронке
        </Link>
      </div>
    );
  }

  const isWon = !!displayStage?.is_won;
  const isLost = !!displayStage?.is_lost;
  const closedAt = isWon ? lead.won_at : isLost ? lead.lost_at : null;
  const isClosed = isWon || isLost;
  const wonStage = stages.find((s) => s.is_won) ?? null;
  const lostStageRef = stages.find((s) => s.is_lost) ?? null;

  function handleCloseWon() {
    if (!wonStage) return;
    // Soft-gate advisory: route the Won close through the same GateModal
    // surface as every other stage move. The modal shows unmet readiness
    // criteria as a NON-blocking warning — the manager always proceeds via
    // «Переместить» (server never blocks a Won move). See B1.
    setGateTarget(wonStage);
  }

  function handleCloseLost() {
    if (!lostStageRef) return;
    setLostStage(lostStageRef);
  }

  return (
    <div className="font-sans min-h-screen bg-brand-bg flex flex-col">
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TabKey)}>
      {/* Sticky header — 2 rows per spec */}
      <header className="sticky top-0 z-20 bg-white border-b border-brand-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-2.5 pb-2">
          <LeadCardHeader
            lead={lead}
            stages={stages}
            displayStage={displayStage}
            meId={me?.id}
            mergedFromCount={mergedFromCount}
            isClosed={isClosed}
            isWon={isWon}
            isLost={isLost}
            closedAt={closedAt}
            wonStage={wonStage}
            lostStageRef={lostStageRef}
            claimPending={claim.isPending}
            unclaimPending={unclaim.isPending}
            onClaim={handleClaim}
            onReturnToPool={handleReturnToPool}
            onTransfer={() => setTransferOpen(true)}
            onCloseWon={handleCloseWon}
            onCloseLost={handleCloseLost}
            onFindDuplicates={() => setDupOpen(true)}
            onDelete={() => setDeleteOpen(true)}
            onStageSelect={handleStageSelect}
            onRename={(name) => updateLead.mutate({ company_name: name })}
          />

          {/* Lead Card v2 — stages stepper + deal-value strip,
              mounted between header pills and tabs. Both blocks are
              self-fetching (their own queries) so they don't bloat
              this component. */}
          <div className="mt-2.5">
            <StagesStepper
              leadId={lead.id}
              currentStageDays={lead.current_stage_days}
            />
          </div>
        </div>
      </header>

      {/* Body — two columns: info (left, always visible) + activity (right, tabbed) */}
      {/* AppShell already provides the <main> landmark; this is a content wrapper. */}
      <div className="flex-1 max-w-6xl mx-auto w-full px-4 sm:px-6 py-4 sm:py-6">
        <div className="grid grid-cols-1 md:grid-cols-[340px_minmax(0,1fr)] gap-4 md:gap-6">
          {/* Left column — key info, always visible regardless of the active tab */}
          <div className="min-w-0">
            <LeadLeftColumn
              lead={lead}
              items={items}
              onCreateTaskRequest={() => {
                setActiveTab("activity");
                setComposerModeRequest("task");
              }}
              onOpenTab={(t) => setActiveTab(t as TabKey)}
            />
          </div>

          {/* Right column — tab switcher + the active tab's content */}
          <div className="min-w-0">
            <div className="sm:hidden mb-4">
              <label className="sr-only" htmlFor="lead-tab-select">Раздел</label>
              <select
                id="lead-tab-select"
                value={activeTab}
                onChange={(e) => setActiveTab(e.target.value as TabKey)}
                className={`w-full px-4 py-2.5 type-caption font-semibold bg-white border border-brand-border rounded-full outline-none focus:border-brand-accent transition-colors ${C.color.text}`}
              >
                {TABS.map((tab) => (
                  <option key={tab.key} value={tab.key}>{tab.label}</option>
                ))}
              </select>
            </div>
            <TabsList className="hidden sm:flex mb-4">
              {TABS.map((tab) => (
                <TabsTrigger key={tab.key} value={tab.key}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="activity">
              <UnifiedFeed
                leadId={lead.id}
                composerModeRequest={composerModeRequest}
                onComposerModeRequestConsumed={() => setComposerModeRequest(null)}
              />
            </TabsContent>
            <TabsContent value="tasks"><TasksTab leadId={lead.id} /></TabsContent>
            <TabsContent value="contacts"><ContactsTab lead={lead} /></TabsContent>
            <TabsContent value="quote"><QuoteTab lead={lead} /></TabsContent>
            <TabsContent value="notes"><NotesTab leadId={lead.id} /></TabsContent>
            <TabsContent value="archive"><ArchiveTab leadId={lead.id} /></TabsContent>
          </div>
        </div>
      </div>
      </Tabs>

      {/* Modals */}
      {gateTarget && (
        <GateModal
          leadId={lead.id}
          targetStage={gateTarget}
          fallbackCriteria={
            gateTarget.is_won
              ? DEFAULT_GATE_CRITERIA[
                  Math.max(
                    0,
                    ...stages
                      .filter((s) => !s.is_won && !s.is_lost)
                      .map((s) => s.position),
                  )
                ] ?? []
              : undefined
          }
          onClose={() => setGateTarget(null)}
          onSuccess={() => {
            if (gateTarget.is_won) showToast("Сделка отмечена выигранной");
            setGateTarget(null);
          }}
        />
      )}

      {transferOpen && (
        <TransferModal
          leadId={lead.id}
          currentAssignedTo={lead.assigned_to ?? null}
          onClose={() => setTransferOpen(false)}
          onSuccess={() => showToast("Лид передан")}
        />
      )}

      {dupOpen && (
        <DuplicatesModal
          leadId={lead.id}
          masterName={lead.company_name}
          onClose={() => setDupOpen(false)}
          onSuccess={(n) =>
            showToast(
              n === 1 ? "1 дубль объединён" : `${n} дублей объединено`,
            )
          }
        />
      )}

      {/* CloseModal removed (Lead Card v2): the «Закрыть сделку ▾»
          dropdown in the header now triggers Won inline or routes Lost
          to LostModal below. */}

      {lostStage && (
        <LostModal
          leadId={lead.id}
          lostStage={lostStage}
          companyName={lead.company_name}
          onClose={() => setLostStage(null)}
          onSuccess={() => showToast("Лид помечен Проигран")}
        />
      )}

      {deleteOpen && (
        <DeleteConfirmModal
          leadId={lead.id}
          companyName={lead.company_name}
          onClose={() => setDeleteOpen(false)}
        />
      )}

      {pendingHref && (
        <NextStepPrompt
          leadId={lead.id}
          company={lead.company_name}
          onSaved={() => {
            const href = pendingHref;
            setPendingHref(null);
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            router.push(href as any);
          }}
          onSkip={() => {
            const href = pendingHref;
            setPendingHref(null);
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            router.push(href as any);
          }}
        />
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-brand-primary text-white type-caption font-semibold px-5 py-2.5 rounded-full z-50 transition">
          {toast}
        </div>
      )}
    </div>
  );
}
