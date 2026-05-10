"use client";
import { useState, useRef } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronDown,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { useLead, useUpdateLead } from "@/lib/hooks/use-lead";
import { usePipelines, DEFAULT_STAGES } from "@/lib/hooks/use-pipelines";
import { useMoveStage, useUnclaimLead } from "@/lib/hooks/use-leads";
import { useMe } from "@/lib/hooks/use-me";
import type { Stage } from "@/lib/types";
import { dealTypeLabel, priorityLabel } from "@/lib/i18n";
import { DealTab } from "./DealTab";
import { ContactsTab } from "./ContactsTab";
import { ScoringTab } from "./ScoringTab";
import { ActivityTab } from "./ActivityTab";
import { PilotTab } from "./PilotTab";
import { AIBriefTab } from "./AIBriefTab";
import { FollowupsRail } from "./FollowupsRail";
import { CustomFieldsPanel } from "./CustomFieldsPanel";
import { GateModal } from "./GateModal";
import { LostModal } from "./LostModal";
import { TransferModal } from "./TransferModal";
import { AgentBanner } from "./AgentBanner";
import { SalesCoachDrawer } from "./SalesCoachDrawer";
import { priorityChip } from "@/lib/ui/priority";
import { C } from "@/lib/design-system";

function scoreChipClass(score: number | null | undefined): string {
  if (score == null) return "bg-brand-panel text-brand-muted";
  if (score >= 80) return "bg-brand-soft text-brand-accent-text";
  if (score >= 60) return "bg-warning/10 text-warning";
  return "bg-brand-panel text-brand-muted";
}

function fitChipClass(fit: number | null | undefined): string {
  if (fit == null) return "bg-brand-panel text-brand-muted";
  if (fit >= 8) return "bg-brand-soft text-brand-accent-text";
  if (fit >= 5) return "bg-warning/10 text-warning";
  return "bg-brand-panel text-brand-muted";
}

function formatWonLostDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

type TabKey = "deal" | "ai-brief" | "contacts" | "scoring" | "activity" | "pilot";

const TABS: { key: TabKey; label: string }[] = [
  { key: "deal",     label: "Сделка" },
  { key: "ai-brief", label: "AI Бриф" },
  { key: "contacts", label: "Контакты" },
  { key: "scoring",  label: "Оценка" },
  { key: "activity", label: "Активность" },
  { key: "pilot",    label: "Пилот" },
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
  const me = useMe().data;
  const router = useRouter();

  // `?tab=activity` (and friends) seeds the initial tab when arriving
  // from a deep-link. Only honored once on mount — explicit clicks
  // afterwards drive the state, not the URL.
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const initialTab: TabKey = TABS.some((t) => t.key === tabParam)
    ? (tabParam as TabKey)
    : "activity";
  const [activeTab, setActiveTab] = useState<TabKey>(initialTab);

  // Sales Coach drawer state — Sprint 3.1 Phase D. Open via the
  // floating «🤖 AI Coach» button or the AgentBanner action button.
  const [coachOpen, setCoachOpen] = useState(false);
  const [coachSeed, setCoachSeed] = useState<string | undefined>(undefined);
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [stageDropdownOpen, setStageDropdownOpen] = useState(false);
  const [gateTarget, setGateTarget] = useState<Stage | null>(null);
  const [lostStage, setLostStage] = useState<Stage | null>(null);
  const [transferOpen, setTransferOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const nameInputRef = useRef<HTMLInputElement>(null);

  // Get stages from pipelines or fallback
  const stages: Stage[] =
    pipelinesQuery.data?.[0]?.stages ??
    DEFAULT_STAGES.map((s, i) => ({
      ...s,
      id: `fallback-${i}`,
      pipeline_id: "default",
    }));

  // Find current stage for this lead
  const currentStage = stages.find((s) => s.id === lead?.stage_id);
  // Fallback: match by first stage if no id match (fallback IDs)
  const displayStage = currentStage ?? stages[0];

  const showPilotTab = displayStage ? displayStage.position >= 8 : false;
  const visibleTabs = TABS.filter(
    (t) => t.key !== "pilot" || showPilotTab
  );

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  }

  function startEditName() {
    if (!lead) return;
    setNameValue(lead.company_name);
    setEditingName(true);
    setTimeout(() => nameInputRef.current?.focus(), 50);
  }

  function commitName() {
    const trimmed = nameValue.trim();
    if (trimmed && lead && trimmed !== lead.company_name) {
      updateLead.mutate({ company_name: trimmed });
    }
    setEditingName(false);
  }

  function handleStageSelect(stage: Stage) {
    setStageDropdownOpen(false);
    if (!lead) return;
    // Check if target stage has gate criteria
    const hasCriteria =
      (stage.gate_criteria_json?.length ?? 0) > 0 ||
      stage.position > 0;
    if (hasCriteria) {
      setGateTarget(stage);
    } else {
      moveStage.mutate({ leadId, body: { stage_id: stage.id } });
    }
  }

  function handleWon() {
    const wonStage = stages.find((s) => s.is_won);
    if (!wonStage || !lead) return;
    moveStage.mutate({ leadId, body: { stage_id: wonStage.id } });
  }

  function handleLost() {
    // Sprint 2.6 G3: open the styled `LostModal` instead of the
    // legacy `window.confirm` + `window.prompt` pair. The modal owns
    // the mutation; success closes it via `onSuccess`.
    const lost = stages.find((s) => s.is_lost);
    if (!lost || !lead) return;
    setLostStage(lost);
  }

  function handleReturnToPool() {
    if (!lead || unclaim.isPending) return;
    unclaim.mutate(leadId, {
      onSuccess: () => router.push("/pipeline"),
    });
  }

  if (isLoading) {
    return (
      <div className="font-sans min-h-screen bg-canvas flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-brand-muted" />
      </div>
    );
  }

  if (isError || !lead) {
    return (
      <div className="font-sans min-h-screen bg-canvas flex flex-col items-center justify-center gap-4">
        <AlertTriangle size={24} className="text-rose" />
        <p className={`${C.bodySm} text-rose`}>Лид не найден или ошибка загрузки</p>
        <Link href="/pipeline" className={`${C.bodySm} ${C.color.accent}`}>
          ← Назад к воронке
        </Link>
      </div>
    );
  }

  const isWon = !!displayStage?.is_won;
  const isLost = !!displayStage?.is_lost;
  const closedAt = isWon ? lead.won_at : isLost ? lead.lost_at : null;

  // Priority A pops with the solid brand accent — see PipelineLeadCard
  // for the same convention.
  const priorityClass =
    lead.priority === "A"
      ? "bg-brand-accent text-white"
      : priorityChip(lead.priority);

  return (
    <div className="font-sans min-h-screen bg-canvas flex flex-col">
      {/* Sticky header */}
      <header className="sticky top-0 z-20 bg-white border-b border-brand-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3">
          <div className="flex flex-wrap items-start gap-3 sm:gap-4">
            {/* Back */}
            <Link
              href="/pipeline"
              className="mt-1 p-1.5 rounded-full text-brand-muted transition-colors shrink-0"
              aria-label="Назад"
            >
              <ArrowLeft size={18} />
            </Link>

            {/* Company name — editable */}
            <div className="flex-1 min-w-0">
              {editingName ? (
                <input
                  ref={nameInputRef}
                  value={nameValue}
                  onChange={(e) => setNameValue(e.target.value)}
                  onBlur={commitName}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitName();
                    if (e.key === "Escape") setEditingName(false);
                  }}
                  className={`${C.cardTitle} font-bold tracking-tight ${C.color.text} bg-transparent border-b-2 border-brand-accent outline-none w-full`}
                />
              ) : (
                <h1
                  onClick={startEditName}
                  className={`${C.cardTitle} font-bold tracking-tight ${C.color.text} cursor-text transition-colors truncate`}
                  title="Нажмите для редактирования"
                >
                  {lead.company_name}
                </h1>
              )}

              {/* Status chips row */}
              <div className="flex flex-wrap items-center gap-2 mt-1.5">
                {/* Stage chip */}
                <span
                  className={`${C.bodyXs} font-semibold px-2.5 py-1 rounded-full text-white`}
                  style={{ backgroundColor: displayStage?.color ?? "#a1a1a6" }}
                >
                  {displayStage?.name ?? "—"}
                </span>

                {/* Priority */}
                {lead.priority && (
                  <span
                    className={`${C.bodyXs} font-semibold px-2.5 py-0.5 rounded-full ${priorityClass}`}
                  >
                    {priorityLabel(lead.priority)}
                  </span>
                )}

                {/* Deal type */}
                {lead.deal_type && (
                  <span className={`${C.bodyXs} ${C.color.mutedLight} bg-brand-panel px-2.5 py-0.5 rounded-full`}>
                    {dealTypeLabel(lead.deal_type)}
                  </span>
                )}

                {/* Source — Sprint 2.2 G4. Surfaces provenance
                    (form:slug, import:bitrix, manual…) so the manager
                    sees at a glance how the lead landed. */}
                {lead.source && (
                  <span
                    className={`${C.bodyXs} ${C.color.mutedLight} bg-brand-panel px-2.5 py-0.5 rounded-full font-mono truncate max-w-[180px]`}
                    title={`Источник: ${lead.source}`}
                  >
                    {lead.source}
                  </span>
                )}

                {/* Score */}
                <span
                  className={`font-mono ${C.bodyXs} font-semibold px-2.5 py-0.5 rounded-full tabular-nums ${scoreChipClass(lead.score)}`}
                  title="0–100, weighted scoring"
                >
                  {lead.score ?? "—"}/100
                </span>

                {/* fit_score */}
                {lead.fit_score != null && (
                  <span
                    className={`font-mono ${C.bodyXs} font-semibold px-2.5 py-0.5 rounded-full tabular-nums ${fitChipClass(Number(lead.fit_score))}`}
                    title="AI fit_score, 0–10"
                  >
                    AI {lead.fit_score}/10
                  </span>
                )}

                {/* Rotting */}
                {(lead.is_rotting_stage || lead.is_rotting_next_step) && (
                  <span className={`flex items-center gap-1 ${C.bodyXs} text-warning`}>
                    <AlertTriangle size={12} />
                    Протухает
                  </span>
                )}
              </div>
            </div>

            {/* Right actions — wraps onto a second line on narrow viewports */}
            <div className="flex flex-wrap items-center gap-2 mt-1 w-full sm:w-auto sm:shrink-0">
              {/* Return to pool — only visible when the current user
                  owns the lead. Backend rejects with 403 otherwise, but
                  hiding the button avoids surfacing that error. */}
              {lead.assigned_to === me?.id && (
                <button
                  onClick={handleReturnToPool}
                  disabled={unclaim.isPending}
                  className={`px-4 py-1.5 ${C.btnLg} font-semibold ${C.button.ghost} disabled:opacity-40 disabled:cursor-not-allowed transition-opacity`}
                >
                  Вернуть в базу
                </button>
              )}

              {/* Transfer */}
              <button
                onClick={() => setTransferOpen(true)}
                className={`px-4 py-1.5 ${C.btnLg} font-semibold ${C.button.ghost} transition-opacity`}
              >
                Передать
              </button>

              {/* Won */}
              <button
                onClick={handleWon}
                disabled={moveStage.isPending || isWon}
                className={`px-4 py-1.5 ${C.btnLg} font-semibold bg-success text-white rounded-full disabled:opacity-40 disabled:cursor-not-allowed transition-opacity`}
              >
                Выиграна
              </button>

              {/* Lost */}
              <button
                onClick={handleLost}
                disabled={moveStage.isPending || isLost}
                className={`px-4 py-1.5 ${C.btnLg} font-semibold bg-rose text-white rounded-full disabled:opacity-40 disabled:cursor-not-allowed transition-opacity`}
              >
                Проиграна
              </button>

              {/* Move stage dropdown */}
              <div className="relative">
                <button
                  onClick={() => setStageDropdownOpen((v) => !v)}
                  className={`flex items-center gap-1.5 px-4 py-1.5 ${C.btnLg} font-semibold bg-brand-primary text-white rounded-full transition-opacity`}
                >
                  Сменить стадию
                  <ChevronDown size={13} />
                </button>
                {stageDropdownOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-10"
                      onClick={() => setStageDropdownOpen(false)}
                    />
                    <div className="absolute right-0 top-full mt-1.5 w-56 bg-white border border-brand-border rounded-2xl z-20 overflow-hidden">
                      {stages
                        .filter((s) => !s.is_won && !s.is_lost)
                        .map((stage) => (
                          <button
                            key={stage.id}
                            onClick={() => handleStageSelect(stage)}
                            className={`flex items-center gap-2.5 w-full px-4 py-2.5 ${C.bodySm} text-left transition-colors ${
                              stage.id === lead.stage_id ? "bg-brand-bg" : ""
                            }`}
                          >
                            <span
                              className="w-2 h-2 rounded-full shrink-0"
                              style={{ backgroundColor: stage.color }}
                            />
                            <span
                              className={
                                stage.id === lead.stage_id
                                  ? `font-semibold ${C.color.text}`
                                  : `${C.color.text}`
                              }
                            >
                              {stage.name}
                            </span>
                          </button>
                        ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Won / Lost banner — only shown after the lead has actually
              entered a terminal stage. Sits between chips/actions and the
              tab switcher so it can't be missed. */}
          {(isWon || isLost) && (
            <div
              className={`mt-3 flex items-center gap-2 px-3 py-2 rounded-2xl ${C.bodyXs} font-semibold ${
                isWon
                  ? "bg-success/10 text-success"
                  : "bg-rose/10 text-rose"
              }`}
            >
              {isWon ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
              <span>
                {isWon ? "Сделка выиграна" : "Сделка проиграна"}
                {closedAt && ` · ${formatWonLostDate(closedAt)}`}
                {isLost && lead.lost_reason && ` · ${lead.lost_reason}`}
              </span>
            </div>
          )}

          {/* Tab switcher — <select> on mobile, horizontal strip on sm+ */}
          <div className="sm:hidden mt-4">
            <label className="sr-only" htmlFor="lead-tab-select">Раздел</label>
            <select
              id="lead-tab-select"
              value={activeTab}
              onChange={(e) => setActiveTab(e.target.value as TabKey)}
              className={`w-full px-4 py-2.5 ${C.bodySm} font-semibold bg-white border border-brand-border rounded-full outline-none focus:border-brand-accent transition-colors ${C.color.text}`}
            >
              {visibleTabs.map((tab) => (
                <option key={tab.key} value={tab.key}>{tab.label}</option>
              ))}
            </select>
          </div>
          <div className="hidden sm:flex gap-0 mt-4 border-b border-brand-border -mb-px overflow-x-auto">
            {visibleTabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-4 py-2.5 ${C.bodySm} font-semibold border-b-2 transition-all whitespace-nowrap ${
                  activeTab === tab.key
                    ? "border-brand-accent text-brand-accent-text"
                    : "border-transparent text-brand-muted"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Body
          Two-column grid: fixed 296px rail (Follow-ups) + flex-1 main column.
          items-start keeps both columns top-aligned regardless of content height.
          gap-6 (24px) between columns matches the design spec.
          KB rail panel removed (Option a): no frontend data flows into it yet;
          KB matches will surface as chips inside the AI Brief result body (Phase G). */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 sm:px-6 py-4 sm:py-6">
        {/* Lead AI Agent banner — Sprint 3.1 Phase D. Sits between
            the sticky header and the rail/tab body. Hides itself
            when there is no cached suggestion. The action button
            opens the Sales Coach drawer with a seed question. */}
        <AgentBanner
          leadId={lead.id}
          onAction={() => {
            setCoachSeed("Что делать дальше по этой карточке?");
            setCoachOpen(true);
          }}
        />

        {/* Single column on < md (rail stacks ABOVE tab body so the user
            sees follow-ups first); side-by-side on md+. min-w-0 on the
            main column lets long content (tables, AI Brief paragraphs)
            wrap instead of forcing horizontal scroll. */}
        <div className="flex flex-col md:flex-row md:items-start md:gap-6 gap-4">
          {/* Rail — 296px fixed on desktop, full-width strip on mobile */}
          <div className="w-full md:w-[296px] md:shrink-0 flex flex-col gap-4">
            <FollowupsRail leadId={lead.id} />
            {/* Sprint 2.6 G4 — workspace custom-attribute values rendered
                inline below the follow-ups rail. Section renders nothing
                when the workspace has no definitions. */}
            <CustomFieldsPanel leadId={lead.id} />
          </div>

          {/* Tab body */}
          <div className="flex-1 min-w-0">
            {activeTab === "deal" && <DealTab lead={lead} />}
            {activeTab === "ai-brief" && <AIBriefTab leadId={lead.id} />}
            {activeTab === "contacts" && <ContactsTab lead={lead} />}
            {activeTab === "scoring" && <ScoringTab lead={lead} />}
            {activeTab === "activity" && <ActivityTab leadId={lead.id} lead={lead} />}
            {activeTab === "pilot" && showPilotTab && <PilotTab lead={lead} />}
          </div>
        </div>
      </main>

      {/* Gate modal */}
      {gateTarget && (
        <GateModal
          leadId={lead.id}
          targetStage={gateTarget}
          onClose={() => setGateTarget(null)}
          onSuccess={() => {
            setGateTarget(null);
          }}
        />
      )}

      {/* Transfer modal */}
      {transferOpen && (
        <TransferModal
          leadId={lead.id}
          currentAssignedTo={lead.assigned_to ?? null}
          onClose={() => setTransferOpen(false)}
          onSuccess={() => showToast("Лид передан")}
        />
      )}

      {/* Sales Coach drawer — Sprint 3.1 Phase D. Mounted always so
          its open/close transitions are smooth; the component
          short-circuits when `open=false`. Seed message comes from
          the banner's action button or `undefined` for a free-form
          first turn. */}
      <SalesCoachDrawer
        leadId={lead.id}
        open={coachOpen}
        onClose={() => {
          setCoachOpen(false);
          setCoachSeed(undefined);
        }}
        seedMessage={coachSeed}
      />

      {/* Floating «🤖 AI Coach» button — bottom-right of viewport.
          Hidden when the drawer is open so it doesn't peek through
          the backdrop on mobile. */}
      {!coachOpen && (
        <button
          onClick={() => {
            setCoachSeed(undefined);
            setCoachOpen(true);
          }}
          aria-label="Открыть Sales Coach"
          className={`fixed bottom-6 right-6 z-30 ${C.button.primary} ${C.btnLg} px-4 py-3 rounded-full shadow-lg flex items-center gap-2`}
        >
          <span aria-hidden>🤖</span>
          <span>AI Coach</span>
        </button>
      )}

      {/* Sprint 2.6 G3: Lost-confirmation modal — replaces the prior
          window.confirm + window.prompt pair. */}
      {lostStage && (
        <LostModal
          leadId={lead.id}
          lostStage={lostStage}
          companyName={lead.company_name}
          onClose={() => setLostStage(null)}
          onSuccess={() => showToast("Лид помечен Проигран")}
        />
      )}

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-6 left-1/2 -translate-x-1/2 bg-brand-primary text-white ${C.bodySm} font-semibold px-5 py-2.5 rounded-full z-50 transition-all`}>
          {toast}
        </div>
      )}
    </div>
  );
}
