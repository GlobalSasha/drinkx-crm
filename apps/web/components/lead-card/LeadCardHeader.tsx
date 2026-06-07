"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  Globe,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Send,
  Lock,
  Trash2,
  MoreHorizontal,
  Star,
  Calendar,
  Activity as ActivityIcon,
  Users,
  GitMerge,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/DropdownMenu";
import { Button } from "@/components/ui/Button";
import { C } from "@/lib/design-system";
import type { LeadOut, Stage } from "@/lib/types";

// Priority pill colors keyed on the letter (A/B/C/D). The visible label is the
// Russian word from `lead.priority_label` (server-side); the background tone
// still varies by letter to keep the visual hierarchy. A is brand-loud; D fades.
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

interface Props {
  lead: LeadOut;
  stages: Stage[];
  displayStage: Stage | undefined;
  meId: string | undefined;
  mergedFromCount: number;
  isClosed: boolean;
  isWon: boolean;
  isLost: boolean;
  closedAt: string | null;
  wonStage: Stage | null;
  lostStageRef: Stage | null;
  claimPending: boolean;
  unclaimPending: boolean;
  onClaim: () => void;
  onReturnToPool: () => void;
  onTransfer: () => void;
  onCloseWon: () => void;
  onCloseLost: () => void;
  onFindDuplicates: () => void;
  onDelete: () => void;
  onStageSelect: (stage: Stage) => void;
  onRename: (name: string) => void;
}

/**
 * Sticky-header content for the Lead Card (rows 1–3 + the Won/Lost banner).
 * Extracted from LeadCard.tsx (BACKLOG #3 part B) — pure presentational split,
 * no behaviour change. Owns the header-local UI state (name editing + the stage
 * dropdown); everything else arrives via props.
 */
export function LeadCardHeader({
  lead,
  stages,
  displayStage,
  meId,
  mergedFromCount,
  isClosed,
  isWon,
  isLost,
  closedAt,
  wonStage,
  lostStageRef,
  claimPending,
  unclaimPending,
  onClaim,
  onReturnToPool,
  onTransfer,
  onCloseWon,
  onCloseLost,
  onFindDuplicates,
  onDelete,
  onStageSelect,
  onRename,
}: Props) {
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [stageDropdownOpen, setStageDropdownOpen] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);

  const priorityClass = priorityPillStyle(lead.priority);

  function startEditName() {
    setNameValue(lead.company_name);
    setEditingName(true);
    setTimeout(() => nameInputRef.current?.focus(), 50);
  }

  function commitName() {
    const trimmed = nameValue.trim();
    if (trimmed && trimmed !== lead.company_name) {
      onRename(trimmed);
    }
    setEditingName(false);
  }

  return (
    <>
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
              className="text-4xl font-bold tracking-tight text-ink bg-transparent border-b-2 border-brand-accent outline-none w-full"
              style={{ lineHeight: "1.2" }}
            />
          ) : (
            <h1
              onClick={startEditName}
              className="text-4xl font-bold tracking-tight text-ink cursor-text hover:text-brand-accent-text transition-colors truncate"
              style={{ lineHeight: "1.2" }}
              title="Нажмите для редактирования"
            >
              {lead.company_name}
            </h1>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {lead.assignment_status === "pool" && (
            <Button
              variant="primary"
              size="sm"
              onClick={onClaim}
              disabled={claimPending}
              className="font-semibold hover:bg-brand-accent/90 active:scale-[0.98]"
            >
              {claimPending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : null}
              Взять в работу
            </Button>
          )}
          {lead.assigned_to === meId && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onReturnToPool}
              disabled={unclaimPending}
              className="font-semibold"
            >
              Вернуть в базу
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onTransfer}
            className="font-semibold"
          >
            <Send size={13} />
            Передать
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                disabled={isClosed}
                className="font-semibold disabled:cursor-not-allowed"
              >
                <Lock size={13} />
                Закрыть сделку
                <ChevronDown size={11} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuItem
                onSelect={onCloseWon}
                disabled={!wonStage}
                className="text-success hover:bg-success/5 focus:bg-success/5"
              >
                <CheckCircle2 size={13} className="text-success" />
                Закрыть как выигран
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={onCloseLost}
                disabled={!lostStageRef}
                className="text-rose hover:bg-rose/5 focus:bg-rose/5"
              >
                <XCircle size={13} className="text-rose" />
                Закрыть как проигран (с причиной)
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Ещё действия">
                <MoreHorizontal size={16} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem onSelect={onFindDuplicates}>
                <Users size={13} />
                Найти дубли
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem destructive onSelect={onDelete}>
                <Trash2 size={13} />
                Удалить лида
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Row 2: meta — primary LPR + key dates. Hidden if nothing to show so
          the header collapses gracefully on bare leads. */}
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
        <DropdownMenu open={stageDropdownOpen} onOpenChange={setStageDropdownOpen}>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              disabled={isClosed}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-semibold text-white text-xs bg-brand-primary hover:opacity-90 transition-opacity disabled:opacity-50"
              style={{ backgroundColor: displayStage?.color ?? "#3b82f6" }}
            >
              <ArrowRight size={11} />
              {displayStage?.name ?? "—"}
              <ChevronDown size={11} />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            {stages
              .filter((s) => !s.is_won && !s.is_lost)
              .map((stage) => (
                <DropdownMenuItem
                  key={stage.id}
                  onSelect={() => onStageSelect(stage)}
                  className={stage.id === lead.stage_id ? "bg-brand-bg" : ""}
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: stage.color }}
                  />
                  <span className={stage.id === lead.stage_id ? "font-semibold" : ""}>
                    {stage.name}
                  </span>
                </DropdownMenuItem>
              ))}
          </DropdownMenuContent>
        </DropdownMenu>

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

        {mergedFromCount > 0 && (
          <span
            className="inline-flex items-center gap-1 type-caption text-brand-muted bg-brand-panel px-2 py-0.5 rounded-full"
            title="Этот лид поглотил дубликаты"
          >
            <GitMerge size={11} />
            объединён из {mergedFromCount}
          </span>
        )}

        {(lead.is_rotting_stage || lead.is_rotting_next_step) && (
          <span className="flex items-center gap-1 type-caption text-warning">
            <AlertTriangle size={11} />
            Протухает
          </span>
        )}

        {lead.source_form_id && lead.source_form_name && (
          <Link
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            href={`/leads-pool?form_id=${lead.source_form_id}` as any}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-brand-soft text-brand-accent-text text-xs font-semibold hover:bg-brand-soft/80 transition-colors"
            title="Открыть пул лидов этого лендинга"
          >
            <Globe size={11} aria-hidden />
            Лендинг: {lead.source_form_name}
          </Link>
        )}
        {lead.source?.startsWith("form:") && !lead.source_form_name && (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-brand-panel text-brand-muted text-xs font-semibold"
            title="Форма удалена"
          >
            <Globe size={11} aria-hidden />
            Заявка с формы
          </span>
        )}
      </div>

      {(isWon || isLost) && (
        <div
          className={`mt-3 ml-9 flex items-center gap-2 px-3 py-2 rounded-card type-caption font-semibold ${
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
    </>
  );
}
