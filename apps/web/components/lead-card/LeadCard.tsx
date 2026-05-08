"use client";
import { useState, useRef } from "react";
import Link from "next/link";
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
import { useMoveStage } from "@/lib/hooks/use-leads";
import type { Stage } from "@/lib/types";
import { dealTypeLabel, priorityLabel } from "@/lib/i18n";
import { DealTab } from "./DealTab";
import { ContactsTab } from "./ContactsTab";
import { ScoringTab } from "./ScoringTab";
import { ActivityTab } from "./ActivityTab";
import { PilotTab } from "./PilotTab";
import { AIBriefTab } from "./AIBriefTab";
import { FollowupsRail } from "./FollowupsRail";
import { GateModal } from "./GateModal";
import { TransferModal } from "./TransferModal";

const PRIORITY_STYLES: Record<string, string> = {
  A: "bg-accent/10 text-accent",
  B: "bg-warning/10 text-warning",
  C: "bg-canvas text-muted",
  D: "bg-black/5 text-muted-2",
};

function scoreChipClass(score: number | null | undefined): string {
  if (score == null) return "bg-black/5 text-muted-2";
  if (score >= 80) return "bg-success/10 text-success";
  if (score >= 60) return "bg-warning/10 text-warning";
  return "bg-black/5 text-muted-2";
}

function fitChipClass(fit: number | null | undefined): string {
  if (fit == null) return "bg-black/5 text-muted-2";
  if (fit >= 8) return "bg-success/10 text-success";
  if (fit >= 5) return "bg-warning/10 text-warning";
  return "bg-black/5 text-muted-2";
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
  { key: "ai-brief", label: "AI Brief" },
  { key: "contacts", label: "Контакты" },
  { key: "scoring",  label: "Scoring" },
  { key: "activity", label: "Активность" },
  { key: "pilot",    label: "Pilot" },
];

interface Props {
  leadId: string;
}

export function LeadCard({ leadId }: Props) {
  const { data: lead, isLoading, isError } = useLead(leadId);
  const pipelinesQuery = usePipelines();
  const updateLead = useUpdateLead(leadId);
  const moveStage = useMoveStage();

  const [activeTab, setActiveTab] = useState<TabKey>("deal");
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [stageDropdownOpen, setStageDropdownOpen] = useState(false);
  const [gateTarget, setGateTarget] = useState<Stage | null>(null);
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
    const lostStage = stages.find((s) => s.is_lost);
    if (!lostStage || !lead) return;
    if (!window.confirm("Перевести в Проиграно?")) return;
    const reason = prompt("Причина закрытия:");
    if (reason === null) return;
    moveStage.mutate({
      leadId,
      body: { stage_id: lostStage.id, lost_reason: reason || null },
    });
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-muted-2" />
      </div>
    );
  }

  if (isError || !lead) {
    return (
      <div className="min-h-screen bg-canvas flex flex-col items-center justify-center gap-4">
        <AlertTriangle size={24} className="text-rose" />
        <p className="text-sm text-rose">Лид не найден или ошибка загрузки</p>
        <Link
          href="/pipeline"
          className="text-sm text-accent hover:underline"
        >
          ← Назад к воронке
        </Link>
      </div>
    );
  }

  const isWon = !!displayStage?.is_won;
  const isLost = !!displayStage?.is_lost;
  const closedAt = isWon ? lead.won_at : isLost ? lead.lost_at : null;

  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      {/* Sticky header */}
      <header className="sticky top-0 z-20 bg-white border-b border-black/5 shadow-soft">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3">
          <div className="flex flex-wrap items-start gap-3 sm:gap-4">
            {/* Back */}
            <Link
              href="/pipeline"
              className="mt-1 p-1.5 rounded-lg hover:bg-canvas text-muted transition-colors shrink-0"
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
                  className="text-xl sm:text-2xl font-extrabold tracking-tight text-ink bg-transparent border-b-2 border-accent outline-none w-full"
                />
              ) : (
                <h1
                  onClick={startEditName}
                  className="text-xl sm:text-2xl font-extrabold tracking-tight text-ink cursor-text hover:text-ink/80 transition-colors truncate"
                  title="Нажмите для редактирования"
                >
                  {lead.company_name}
                </h1>
              )}

              {/* Status chips row */}
              <div className="flex flex-wrap items-center gap-2 mt-1.5">
                {/* Stage chip */}
                <span
                  className="text-xs font-semibold px-2.5 py-1 rounded-pill text-white"
                  style={{ backgroundColor: displayStage?.color ?? "#a1a1a6" }}
                >
                  {displayStage?.name ?? "—"}
                </span>

                {/* Priority */}
                {lead.priority && (
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded-md ${
                      PRIORITY_STYLES[lead.priority] ?? "bg-black/5 text-muted"
                    }`}
                  >
                    {priorityLabel(lead.priority)}
                  </span>
                )}

                {/* Deal type */}
                {lead.deal_type && (
                  <span className="text-xs text-muted-2 bg-black/5 px-2 py-0.5 rounded-md">
                    {dealTypeLabel(lead.deal_type)}
                  </span>
                )}

                {/* Source — Sprint 2.2 G4. Surfaces provenance
                    (form:slug, import:bitrix, manual…) so the manager
                    sees at a glance how the lead landed. */}
                {lead.source && (
                  <span
                    className="text-xs text-muted-2 bg-black/5 px-2 py-0.5 rounded-md font-mono truncate max-w-[180px]"
                    title={`Источник: ${lead.source}`}
                  >
                    {lead.source}
                  </span>
                )}

                {/* Score */}
                <span
                  className={`font-mono text-xs font-semibold px-2 py-0.5 rounded-md tabular-nums ${scoreChipClass(lead.score)}`}
                  title="0–100, weighted scoring"
                >
                  {lead.score ?? "—"}/100
                </span>

                {/* fit_score */}
                {lead.fit_score != null && (
                  <span
                    className={`font-mono text-xs font-semibold px-2 py-0.5 rounded-md tabular-nums ${fitChipClass(Number(lead.fit_score))}`}
                    title="AI fit_score, 0–10"
                  >
                    AI {lead.fit_score}/10
                  </span>
                )}

                {/* Rotting */}
                {(lead.is_rotting_stage || lead.is_rotting_next_step) && (
                  <span className="flex items-center gap-1 text-xs text-warning">
                    <AlertTriangle size={12} />
                    Протухает
                  </span>
                )}
              </div>
            </div>

            {/* Right actions — wraps onto a second line on narrow viewports */}
            <div className="flex flex-wrap items-center gap-2 mt-1 w-full sm:w-auto sm:shrink-0">
              {/* Transfer */}
              <button
                onClick={() => setTransferOpen(true)}
                className="px-3 py-1.5 text-sm font-semibold text-muted bg-canvas border border-black/10 rounded-pill hover:bg-canvas-2 transition-all"
              >
                Передать
              </button>

              {/* Won */}
              <button
                onClick={handleWon}
                disabled={moveStage.isPending || isWon}
                className="px-3 py-1.5 text-sm font-semibold bg-success text-white rounded-pill hover:bg-success/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                Выиграна
              </button>

              {/* Lost */}
              <button
                onClick={handleLost}
                disabled={moveStage.isPending || isLost}
                className="px-3 py-1.5 text-sm font-semibold bg-rose text-white rounded-pill hover:bg-rose/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                Проиграна
              </button>

              {/* Move stage dropdown */}
              <div className="relative">
                <button
                  onClick={() => setStageDropdownOpen((v) => !v)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-semibold bg-ink text-white rounded-pill hover:bg-ink/90 transition-all"
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
                    <div className="absolute right-0 top-full mt-1.5 w-56 bg-white border border-black/10 rounded-2xl shadow-soft z-20 overflow-hidden">
                      {stages
                        .filter((s) => !s.is_won && !s.is_lost)
                        .map((stage) => (
                          <button
                            key={stage.id}
                            onClick={() => handleStageSelect(stage)}
                            className={`flex items-center gap-2.5 w-full px-4 py-2.5 text-sm text-left hover:bg-canvas transition-colors ${
                              stage.id === lead.stage_id ? "bg-canvas" : ""
                            }`}
                          >
                            <span
                              className="w-2 h-2 rounded-full shrink-0"
                              style={{ backgroundColor: stage.color }}
                            />
                            <span
                              className={
                                stage.id === lead.stage_id
                                  ? "font-semibold text-ink"
                                  : "text-ink"
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
              className={`mt-3 flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold ${
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
              className="w-full px-3 py-2.5 text-sm font-semibold bg-canvas border border-black/10 rounded-pill outline-none focus:border-accent/40 transition-colors"
            >
              {visibleTabs.map((tab) => (
                <option key={tab.key} value={tab.key}>{tab.label}</option>
              ))}
            </select>
          </div>
          <div className="hidden sm:flex gap-0 mt-4 border-b border-black/5 -mb-px overflow-x-auto">
            {visibleTabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-4 py-2.5 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
                  activeTab === tab.key
                    ? "border-accent text-accent"
                    : "border-transparent text-muted-2 hover:text-ink"
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
        {/* Single column on < md (rail stacks ABOVE tab body so the user
            sees follow-ups first); side-by-side on md+. min-w-0 on the
            main column lets long content (tables, AI Brief paragraphs)
            wrap instead of forcing horizontal scroll. */}
        <div className="flex flex-col md:flex-row md:items-start md:gap-6 gap-4">
          {/* Rail — 296px fixed on desktop, full-width strip on mobile */}
          <div className="w-full md:w-[296px] md:shrink-0 flex flex-col gap-4">
            <FollowupsRail leadId={lead.id} />
          </div>

          {/* Tab body */}
          <div className="flex-1 min-w-0">
            {activeTab === "deal" && <DealTab lead={lead} />}
            {activeTab === "ai-brief" && <AIBriefTab leadId={lead.id} />}
            {activeTab === "contacts" && <ContactsTab lead={lead} />}
            {activeTab === "scoring" && <ScoringTab lead={lead} />}
            {activeTab === "activity" && <ActivityTab leadId={lead.id} />}
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

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-ink text-white text-sm font-semibold px-5 py-2.5 rounded-pill shadow-soft z-50 transition-all">
          {toast}
        </div>
      )}
    </div>
  );
}
