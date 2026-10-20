"use client";

import { Check, Loader2 } from "lucide-react";
import { useStageDurations } from "@/lib/hooks/use-lead-v2";

interface Props {
  leadId: string;
  // Authoritative days-on-current-stage from LeadOut (read path). Falls
  // back to the per-stage `days` from the durations endpoint if absent.
  currentStageDays?: number | null;
  // Лид застрял на этапе — дни подсвечиваются предупреждением.
  isRotting?: boolean;
}

/**
 * Funnel stepper for the LeadCard header.
 *
 * One node per stage on a track: done stages are filled with a check, the
 * current one is ringed, pending ones are hollow. The first node sits on the
 * left edge and the last on the right edge of the header column, so the
 * stepper keeps the same grid as the body below. Under each node (sm+) —
 * stage name and days spent there; on phones the labels don't fit, so a
 * one-line caption replaces them.
 */
export function StagesStepper({ leadId, currentStageDays, isRotting }: Props) {
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
  // node so the stepper still reads as "fully advanced" rather than empty.
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
  const daysTone = isRotting ? "text-warning" : "text-brand-accent-text";

  // Track runs between the centres of the first and last nodes (12px = half
  // a 24px node); the filled part ends at the current node.
  const fillPct = total > 1 ? Math.max(0, fillIdx) / (total - 1) : 0;

  return (
    <div>
      <ol
        className="relative flex items-start justify-between sm:pb-10"
        role="progressbar"
        aria-valuemin={1}
        aria-valuemax={total}
        aria-valuenow={Math.max(1, fillIdx + 1)}
        aria-label="Прогресс по воронке"
      >
        <span
          className="absolute left-3 right-3 top-3 h-0.5 -translate-y-1/2 rounded-full bg-brand-panel"
          aria-hidden
        />
        <span
          className="absolute left-3 top-3 h-0.5 -translate-y-1/2 rounded-full bg-brand-accent"
          style={{ width: `calc((100% - 24px) * ${fillPct})` }}
          aria-hidden
        />

        {stages.map((s, i) => {
          const isDone = s.status === "done";
          const isCurrent = i === currentIdx;
          const days = isCurrent ? curDays : s.days;
          const align =
            i === 0
              ? "left-0 text-left"
              : i === total - 1
                ? "right-0 text-right"
                : "left-1/2 -translate-x-1/2 text-center";
          return (
            <li
              key={s.stage_id}
              className="relative"
              title={
                s.days != null
                  ? `${s.stage_name} · ${s.days} ${pluralDays(s.days)}`
                  : s.stage_name
              }
            >
              <span
                className={`relative z-10 flex items-center justify-center w-6 h-6 rounded-full ${
                  isDone
                    ? "bg-brand-accent text-white"
                    : isCurrent
                      ? "bg-white border-2 border-brand-accent ring-4 ring-brand-soft"
                      : "bg-white border-2 border-brand-panel"
                }`}
              >
                {isDone && <Check size={12} strokeWidth={3} />}
                {isCurrent && <span className="w-2 h-2 rounded-full bg-brand-accent" />}
              </span>
              <span
                className={`hidden sm:block absolute top-8 w-28 ${align}`}
              >
                <span
                  className={`block truncate type-caption font-semibold ${
                    isCurrent
                      ? "text-brand-primary"
                      : isDone
                        ? "text-brand-muted-strong"
                        : "text-brand-muted"
                  }`}
                >
                  {s.stage_name}
                </span>
                {days != null && (
                  <span
                    className={`block text-xs tabular-nums ${
                      isCurrent ? `font-semibold ${daysTone}` : "text-brand-muted"
                    }`}
                  >
                    {days} {pluralDays(days)}
                    {isCurrent && " на этапе"}
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ol>

      {/* Phones: labels don't fit under 7 nodes — one caption instead. */}
      <div className="sm:hidden mt-3 flex items-center justify-between gap-3 type-caption text-brand-muted">
        <span className="min-w-0 truncate tabular-nums">
          {currentIdx !== -1 ? (
            <>
              <span className="font-semibold text-brand-primary">
                {stages[currentIdx].stage_name}
              </span>
              {" · "}
              {currentIdx + 1} из {total}
            </>
          ) : (
            <>{total} этапов</>
          )}
        </span>
        {curDays != null && (
          <span className={`shrink-0 font-semibold tabular-nums ${daysTone}`}>
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
