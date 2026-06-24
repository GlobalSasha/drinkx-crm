"use client";

import { Loader2 } from "lucide-react";
import { useStageDurations } from "@/lib/hooks/use-lead-v2";

interface Props {
  leadId: string;
  // Authoritative days-on-current-stage from LeadOut (read path). Falls
  // back to the per-stage `days` from the durations endpoint if absent.
  currentStageDays?: number | null;
}

/**
 * Compact funnel-progress bar for the LeadCard header.
 *
 * One segmented line (one segment per stage, filled through the current
 * one) plus a caption with funnel position + days-on-stage. The stage
 * NAME and the stage selector live in the «→ Discovery ▾» dropdown above,
 * so this deliberately carries no stage list — it only answers «как далеко
 * по воронке» and «сколько дней на этапе» without duplicating that picker.
 */
export function StagesStepper({ leadId, currentStageDays }: Props) {
  const { data: stages, isLoading, isError } = useStageDurations(leadId);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 type-caption text-brand-muted">
        <Loader2 size={11} className="animate-spin" />
        Загрузка этапов…
      </div>
    );
  }
  if (isError || !stages || stages.length === 0) return null;

  const total = stages.length;
  const currentIdx = stages.findIndex((s) => s.status === "current");
  // Won/lost/detached leads have no «current» — fill through the last done
  // segment so the bar still reads as "fully advanced" rather than empty.
  const lastDoneIdx = stages.reduce(
    (acc, s, i) => (s.status === "done" ? i : acc),
    -1,
  );
  const fillIdx = currentIdx !== -1 ? currentIdx : lastDoneIdx;

  const curDays =
    currentStageDays != null
      ? currentStageDays
      : currentIdx !== -1
        ? stages[currentIdx].days
        : null;

  return (
    <div>
      <div
        className="flex items-center gap-1"
        role="progressbar"
        aria-valuemin={1}
        aria-valuemax={total}
        aria-valuenow={Math.max(1, fillIdx + 1)}
        aria-label="Прогресс по воронке"
      >
        {stages.map((s, i) => (
          <span
            key={s.stage_id}
            title={
              s.days != null
                ? `${s.stage_name} · ${s.days} ${pluralDays(s.days)}`
                : s.stage_name
            }
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              i <= fillIdx ? "bg-brand-accent" : "bg-brand-border"
            }`}
          />
        ))}
      </div>

      <div className="mt-1.5 flex items-center justify-between gap-2 type-caption text-brand-muted">
        <span className="tabular-nums">
          {currentIdx !== -1 ? (
            <>
              Этап {currentIdx + 1} из {total}
            </>
          ) : (
            <>{total} этапов</>
          )}
        </span>
        {curDays != null && (
          <span className="font-semibold text-brand-accent-text tabular-nums">
            {curDays} {pluralDays(curDays)} на этапе
          </span>
        )}
      </div>
    </div>
  );
}

function pluralDays(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "дня";
  return "дней";
}
