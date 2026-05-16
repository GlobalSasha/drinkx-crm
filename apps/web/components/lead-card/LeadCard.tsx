"use client";
import { useState, useRef } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Send,
  Lock,
  Trash2,
  Star,
  Calendar,
  Activity as ActivityIcon,
} from "lucide-react";
import { useLead, useUpdateLead } from "@/lib/hooks/use-lead";
import { usePipelines, DEFAULT_STAGES } from "@/lib/hooks/use-pipelines";
import { useClaimLead, useMoveStage, useUnclaimLead } from "@/lib/hooks/use-leads";
import { useMe } from "@/lib/hooks/use-me";
import type { Stage } from "@/lib/types";
import { DealAndAITab } from "./DealAndAITab";
import { ContactsTab } from "./ContactsTab";
import { UnifiedFeed } from "./feed/UnifiedFeed";
import { FollowupsRail } from "./FollowupsRail";
import { CustomFieldsPanel } from "./CustomFieldsPanel";
import { ClientScoreCard } from "./ClientScoreCard";
import { DealValueStrip } from "./DealValueStrip";
import { StagesStepper } from "./StagesStepper";
import { ResearchGapsCard } from "./ResearchGapsCard";
import { GateModal } from "./GateModal";
import { LostModal } from "./LostModal";
import { TransferModal } from "./TransferModal";
import { DeleteConfirmModal } from "./DeleteConfirmModal";
import { C } from "@/lib/design-system";

// Priority pill colors keyed on the letter (A/B/C/D). Lead Card v2:
// the visible label is now the Russian word from `lead.priority_label`
// (server-side), but the background tone still varies by letter to
// keep the visual hierarchy. Letter A is the brand-loud one; D fades
// to gray.
function priorityPillStyle(letter: string | null | undefined): string {
  switch (letter) {
    case "A":
      return "bg-success/15 text-success";
    case "B":
      return "bg-success/10 text-success";
    case "C":
      return "bg-warning/10 text-warning";
    case "D":
      return "bg-black/5 text-brand-muted";
    default:
      return "bg-black/5 text-brand-muted";
  }
}

function formatRelativeShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
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

// «Переписка» tab is gone (Sprint Unified Activity Feed). Emails now
// appear inside «Активность» as collapsed cards alongside comments /
// tasks / AI messages. Telegram + phone messages stay in `inbox_messages`
// for now — separate sprint will surface them again.
type TabKey = "activity" | "deal-ai" | "contacts";

const TABS: { key: TabKey; label: string }[] = [
  { key: "activity", label: "Активность" },
  { key: "deal-ai", label: "Сделка и AI" },
  { key: "contacts", label: "Контакты" },
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

  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const initialTab: TabKey = TABS.some((t) => t.key === tabParam)
    ? (tabParam as TabKey)
    : "activity";
  const [activeTab, setActiveTab] = useState<TabKey>(initialTab);
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [stageDropdownOpen, setStageDropdownOpen] = useState(false);
  const [gateTarget, setGateTarget] = useState<Stage | null>(null);
  const [lostStage, setLostStage] = useState<Stage | null>(null);
  const [transferOpen, setTransferOpen] = useState(false);
  // Lead Card v2: «Закрыто» button is now a tiny dropdown so the
  // manager picks Won / Lost without going through CloseModal's
  // grid. Won → straight call into useMoveStage; Lost → opens the
  // existing LostModal with the required reason field.
  const [closeMenuOpen, setCloseMenuOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const nameInputRef = useRef<HTMLInputElement>(null);

  const stages: Stage[] =
    pipelinesQuery.data?.[0]?.stages ??
    DEFAULT_STAGES.map((s, i) => ({
      ...s,
      id: `fallback-${i}`,
      pipeline_id: "default",
    }));

  const currentStage = stages.find((s) => s.id === lead?.stage_id);
  const displayStage = currentStage ?? stages[0];

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
      <div className="font-sans min-h-screen bg-canvas flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-brand-muted" />
      </div>
    );
  }

  if (isError || !lead) {
    return (
      <div className="font-sans min-h-screen bg-canvas flex flex-col items-center justify-center gap-4">
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

  const priorityClass = priorityPillStyle(lead.priority);

  function handleCloseWon() {
    setCloseMenuOpen(false);
    if (!wonStage) return;
    moveStage.mutate(
      { leadId: lead!.id, body: { stage_id: wonStage.id } },
      {
        onSuccess: () => showToast("Сделка отмечена выигранной"),
      },
    );
  }

  function handleCloseLost() {
    setCloseMenuOpen(false);
    if (!lostStageRef) return;
    setLostStage(lostStageRef);
  }

  return (
    <div className="font-sans min-h-screen bg-canvas flex flex-col">
      {/* Sticky header — 2 rows per spec */}
      <header className="sticky top-0 z-20 bg-white border-b border-brand-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-3 pb-2">
          {/* Row 1: back + company name + action buttons */}
          <div className="flex items-start gap-3">
            <Link
              href="/pipeline"
              className="mt-1 p-1.5 rounded-full text-brand-muted hover:bg-brand-panel transition-colors shrink-0"
              aria-label="Назад"
            >
              <ArrowLeft size={18} />
            </Link>

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
                  className="text-[22px] font-medium tracking-tight text-ink bg-transparent border-b-2 border-brand-accent outline-none w-full"
                  style={{ lineHeight: "1.2" }}
                />
              ) : (
                <h1
                  onClick={startEditName}
                  className="text-[22px] font-medium tracking-tight text-ink cursor-text hover:text-brand-accent-text transition-colors truncate"
                  style={{ lineHeight: "1.2" }}
                  title="Нажмите для редактирования"
                >
                  {lead.company_name}
                </h1>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 shrink-0">
              {lead.assignment_status === "pool" && (
                <button
                  type="button"
                  onClick={handleClaim}
                  disabled={claim.isPending}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 type-body font-semibold bg-brand-accent text-white rounded-full disabled:opacity-40 transition-opacity hover:bg-brand-accent/90 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg"
                >
                  {claim.isPending ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : null}
                  Взять в работу
                </button>
              )}
              {lead.assigned_to === me?.id && (
                <button
                  type="button"
                  onClick={handleReturnToPool}
                  disabled={unclaim.isPending}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 type-body font-semibold ${C.button.ghost} disabled:opacity-40 transition-opacity`}
                >
                  Вернуть в базу
                </button>
              )}
              <button
                type="button"
                onClick={() => setTransferOpen(true)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 type-body font-semibold ${C.button.ghost} transition-opacity`}
              >
                <Send size={13} />
                Передать
              </button>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setCloseMenuOpen((v) => !v)}
                  disabled={isClosed}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 type-body font-semibold ${C.button.ghost} disabled:opacity-40 disabled:cursor-not-allowed transition-opacity`}
                >
                  <Lock size={13} />
                  Закрыть сделку
                  <ChevronDown size={11} />
                </button>
                {closeMenuOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-10"
                      onClick={() => setCloseMenuOpen(false)}
                    />
                    <div className="absolute right-0 top-full mt-1 w-64 bg-white border border-brand-border rounded-2xl shadow-soft z-20 overflow-hidden">
                      <button
                        type="button"
                        onClick={handleCloseWon}
                        disabled={!wonStage}
                        className="flex w-full items-center gap-2 px-4 py-2.5 text-left type-caption hover:bg-success/5 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <CheckCircle2 size={13} className="text-success" />
                        <span className="font-semibold text-success">
                          Закрыть как выигран
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={handleCloseLost}
                        disabled={!lostStageRef}
                        className="flex w-full items-center gap-2 px-4 py-2.5 text-left type-caption hover:bg-rose/5 disabled:opacity-40 disabled:cursor-not-allowed border-t border-brand-border"
                      >
                        <XCircle size={13} className="text-rose" />
                        <span className="font-semibold text-rose">
                          Закрыть как проигран (с причиной)
                        </span>
                      </button>
                    </div>
                  </>
                )}
              </div>
              <button
                type="button"
                onClick={() => setDeleteOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-semibold text-rose hover:bg-rose/10 rounded-full transition-colors"
              >
                <Trash2 size={13} />
                Удалить
              </button>
            </div>
          </div>

          {/* Row 2: meta — primary LPR + key dates. Hidden if nothing
              to show so the header collapses gracefully on bare leads. */}
          {(lead.primary_contact_name || lead.assigned_at || lead.last_activity_at) && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 ml-9 type-caption text-brand-muted">
              {lead.primary_contact_name && (
                <span className="inline-flex items-center gap-1">
                  <Star size={11} fill="currentColor" className="text-brand-accent" />
                  <span className="text-brand-primary font-semibold">
                    {lead.primary_contact_name}
                  </span>
                </span>
              )}
              {(lead.assigned_at || lead.created_at) && (
                <span className="inline-flex items-center gap-1">
                  <Calendar size={11} />
                  в работе с {formatRelativeShort(lead.assigned_at ?? lead.created_at)}
                </span>
              )}
              {lead.last_activity_at && (
                <span className="inline-flex items-center gap-1">
                  <ActivityIcon size={11} className="text-success" />
                  активность {formatRelativeShort(lead.last_activity_at)}
                </span>
              )}
            </div>
          )}

          {/* Row 3: stage / priority / segment pills */}
          <div className="flex flex-wrap items-center gap-2 mt-3 ml-9">
            <button
              type="button"
              onClick={() => setStageDropdownOpen((v) => !v)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-semibold text-white text-xs bg-brand-primary hover:opacity-90 transition-opacity"
              style={{ backgroundColor: displayStage?.color ?? "#3b82f6" }}
            >
              <ArrowRight size={11} />
              {displayStage?.name ?? "—"}
              <ChevronDown size={11} />
            </button>

            {stageDropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setStageDropdownOpen(false)}
                />
                <div className="absolute left-12 mt-9 w-56 bg-white border border-brand-border rounded-2xl z-20 overflow-hidden shadow-soft">
                  {stages
                    .filter((s) => !s.is_won && !s.is_lost)
                    .map((stage) => (
                      <button
                        key={stage.id}
                        type="button"
                        onClick={() => handleStageSelect(stage)}
                        className={`flex items-center gap-2.5 w-full px-4 py-2.5 type-caption text-brand-muted text-left transition-colors hover:bg-brand-panel ${
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

            <span className="w-px h-4 bg-brand-border" aria-hidden="true" />

            {(lead.priority_label || lead.priority) && (
              <span
                className={`type-caption font-semibold px-2.5 py-0.5 rounded-full ${priorityClass}`}
              >
                {lead.priority_label ?? lead.priority}
              </span>
            )}

            {lead.segment && (
              <span
                className={`type-caption ${C.color.muted} bg-brand-panel px-2 py-0.5 rounded-full`}
              >
                {lead.segment}
              </span>
            )}

            {(lead.is_rotting_stage || lead.is_rotting_next_step) && (
              <span className="flex items-center gap-1 type-caption text-warning">
                <AlertTriangle size={11} />
                Протухает
              </span>
            )}
          </div>

          {(isWon || isLost) && (
            <div
              className={`mt-3 ml-9 flex items-center gap-2 px-3 py-2 rounded-2xl type-caption font-semibold ${
                isWon ? "bg-success/10 text-success" : "bg-rose/10 text-rose"
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

          {/* Lead Card v2 — stages stepper + deal-value strip,
              mounted between header pills and tabs. Both blocks are
              self-fetching (their own queries) so they don't bloat
              this component. */}
          <div className="mt-4">
            <StagesStepper leadId={lead.id} />
          </div>
          <div className="mt-3">
            <DealValueStrip lead={lead} />
          </div>

          {/* Tab switcher */}
          <div className="sm:hidden mt-4">
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
          <div className="hidden sm:flex gap-0 mt-4 border-b border-brand-border -mb-px overflow-x-auto">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`px-4 py-2.5 type-caption font-semibold border-b-2 transition-all whitespace-nowrap ${
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

      {/* Main body — main column LEFT, right column 296px on desktop */}
      {/* AppShell already provides the <main> landmark; this is a content wrapper. */}
      <div className="flex-1 max-w-6xl mx-auto w-full px-4 sm:px-6 py-4 sm:py-6">
        <div className="flex flex-col md:flex-row md:items-start md:gap-6 gap-4">
          {/* Tab body (main) */}
          <div className="flex-1 min-w-0 order-2 md:order-1">
            {activeTab === "activity" && <UnifiedFeed leadId={lead.id} />}
            {activeTab === "deal-ai" && <DealAndAITab lead={lead} />}
            {activeTab === "contacts" && <ContactsTab lead={lead} />}
          </div>

          {/* Right column */}
          <aside className="w-full md:w-[296px] md:shrink-0 flex flex-col gap-4 order-1 md:order-2">
            <FollowupsRail leadId={lead.id} />
            <ClientScoreCard lead={lead} />
            <ResearchGapsCard lead={lead} />
            <CustomFieldsPanel leadId={lead.id} />
          </aside>
        </div>
      </div>

      {/* Modals */}
      {gateTarget && (
        <GateModal
          leadId={lead.id}
          targetStage={gateTarget}
          onClose={() => setGateTarget(null)}
          onSuccess={() => setGateTarget(null)}
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

      {/* AgentBanner + SalesCoachDrawer + FAB removed — Чак now
          lives inside the unified Activity feed as a participant
          (Sprint Unified Activity Feed). Use the feed composer
          with «@Чак ...» to ask a question. */}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-brand-primary text-white type-caption font-semibold px-5 py-2.5 rounded-full z-50 transition-all">
          {toast}
        </div>
      )}
    </div>
  );
}
