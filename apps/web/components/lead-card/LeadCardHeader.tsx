"use client";
import { useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
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
  UserRound,
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
import { useUsers } from "@/lib/hooks/use-users";
import { C } from "@/lib/design-system";
import type { LeadOut, Stage } from "@/lib/types";
import { STAGE_COLOR_FALLBACK } from "@/components/ui/Chart";

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

// Every chip in the header shares one shape and type: 28px pill, caption caps.
const CHIP =
  "inline-flex items-center gap-1.5 h-7 px-3 rounded-full type-caption font-semibold whitespace-nowrap";

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
  // Rendered under the meta row, in the same column as the title
  // (the funnel progress row).
  children?: ReactNode;
}

/**
 * Sticky-header content for the Lead Card (title row, meta row, the Won/Lost
 * banner and the progress slot — all in one column under the title).
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
  children,
}: Props) {
  const usersQuery = useUsers();
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [stageDropdownOpen, setStageDropdownOpen] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const priorityClass = priorityPillStyle(lead.priority);

  // Return to wherever the user actually came from — a manager's scoped
  // pipeline (`/pipeline?assigned_to=…`), the manager deep-dive page, the
  // inbox, /today, or their own board — instead of a hardcoded `/pipeline`.
  // Fall back to `/pipeline` only when there is no in-app history to pop
  // (the lead was opened directly: fresh tab, refresh, or external link).
  function handleBack() {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push("/pipeline");
    }
  }

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

  const owner = usersQuery.data?.items.find((u) => u.id === lead.assigned_to);
  const isNobody = lead.assigned_to == null;
  const isMine = !isNobody && lead.assigned_to === meId;
  const ownerLabel = isNobody
    ? "Ничей — свободен"
    : isMine
      ? "Ваш лид"
      : owner
        ? owner.name || owner.email
        : (lead.assigned_to ?? "").slice(0, 8);
  const ownerTone = isNobody
    ? "bg-white text-brand-muted border border-dashed border-brand-border"
    : isMine
      ? "bg-brand-soft text-brand-accent-text"
      : "bg-brand-panel text-brand-primary";

  return (
    <div>
      {/* Row 1: back + company name + action buttons (stacked on phones so
          the buttons never squeeze the name to zero width). The back arrow
          sits inline with the name, so every row below starts at the same
          left edge as the body columns. */}
      <div className="flex flex-col sm:flex-row sm:items-start gap-3">
        <div className="flex flex-1 min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={handleBack}
            className={`-ml-2 w-9 h-9 inline-flex items-center justify-center rounded-full text-brand-muted hover:bg-brand-panel transition-colors shrink-0 ${C.focusRing}`}
            aria-label="Назад"
          >
            <ArrowLeft size={18} />
          </button>
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
              className="flex-1 min-w-0 type-page-title text-brand-primary bg-transparent border-b-2 border-brand-accent outline-none"
            />
          ) : (
            <h1
              onClick={startEditName}
              className="min-w-0 type-page-title text-brand-primary cursor-text hover:text-brand-accent-text transition-colors truncate"
              title="Нажмите для редактирования"
            >
              {lead.company_name}
            </h1>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:justify-end sm:shrink-0">
          {lead.assignment_status === "pool" && (
            <Button
              variant="primary"
              size="sm"
              onClick={onClaim}
              disabled={claimPending}
              className="h-9 px-4 font-semibold"
            >
              {claimPending ? (
                <Loader2 size={14} className="animate-spin" />
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
              className="h-9 px-4 font-semibold"
            >
              Вернуть в базу
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onTransfer}
            className="h-9 px-4 font-semibold"
          >
            <Send size={14} />
            Передать
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                disabled={isClosed}
                className="h-9 px-4 font-semibold disabled:cursor-not-allowed"
              >
                <Lock size={14} />
                Закрыть сделку
                <ChevronDown size={14} />
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

      {/* Row 2: stage selector, status chips, then plain-text meta. */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <DropdownMenu open={stageDropdownOpen} onOpenChange={setStageDropdownOpen}>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              disabled={isClosed}
              className={`${CHIP} bg-white text-brand-primary border border-brand-border hover:bg-brand-bg transition-colors disabled:opacity-50 ${C.focusRing}`}
            >
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: displayStage?.color ?? STAGE_COLOR_FALLBACK }}
                aria-hidden
              />
              {displayStage?.name ?? "—"}
              <ChevronDown size={12} className="text-brand-muted" />
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

        <span className={`${CHIP} max-w-[14rem] ${ownerTone}`}>
          <UserRound size={12} className="shrink-0" />
          <span className="truncate">{ownerLabel}</span>
        </span>

        {(lead.priority_label || lead.priority) && (
          <span className={`${CHIP} ${priorityClass}`}>
            {lead.priority_label ?? lead.priority}
          </span>
        )}

        {lead.segment && (
          <span className={`${CHIP} bg-brand-panel text-brand-muted-strong`}>
            {lead.segment}
          </span>
        )}

        {(lead.is_rotting_stage || lead.is_rotting_next_step) && (
          <span className={`${CHIP} bg-warning/10 text-warning`}>
            <AlertTriangle size={12} />
            Протухает
          </span>
        )}

        {mergedFromCount > 0 && (
          <span
            className={`${CHIP} bg-brand-panel text-brand-muted`}
            title="Этот лид поглотил дубликаты"
          >
            <GitMerge size={12} />
            объединён из {mergedFromCount}
          </span>
        )}

        {lead.source_form_id && lead.source_form_name && (
          <Link
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            href={`/leads-pool?form_id=${lead.source_form_id}` as any}
            className={`${CHIP} bg-brand-soft text-brand-accent-text hover:bg-brand-soft/80 transition-colors ${C.focusRing}`}
            title="Открыть пул лидов этого лендинга"
          >
            <Globe size={12} aria-hidden />
            Лендинг: {lead.source_form_name}
          </Link>
        )}
        {lead.source?.startsWith("form:") && !lead.source_form_name && (
          <span
            className={`${CHIP} bg-brand-panel text-brand-muted`}
            title="Форма удалена"
          >
            <Globe size={12} aria-hidden />
            Заявка с формы
          </span>
        )}

        <span className="flex flex-wrap items-center gap-x-4 gap-y-1 ml-2 type-caption text-brand-muted">
          {lead.primary_contact_name && (
            <span className="inline-flex items-center gap-1.5">
              <Star size={12} fill="currentColor" className="text-brand-accent" />
              <span className="text-brand-primary font-semibold">
                {lead.primary_contact_name}
              </span>
            </span>
          )}
          {(lead.assigned_at || lead.created_at) && (
            <span className="inline-flex items-center gap-1.5">
              <Calendar size={12} />
              в работе с {formatRelativeShort(lead.assigned_at ?? lead.created_at)}
            </span>
          )}
          {lead.last_activity_at && (
            <span className="inline-flex items-center gap-1.5">
              <ActivityIcon size={12} className="text-success" />
              активность {formatRelativeShort(lead.last_activity_at)}
            </span>
          )}
        </span>
      </div>

      {(isWon || isLost) && (
        <div
          className={`mt-3 flex items-center gap-2 px-3 py-1.5 rounded-full type-caption font-semibold ${
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

      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}
