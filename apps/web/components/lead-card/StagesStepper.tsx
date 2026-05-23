"use client";

import { useState } from "react";
import { Check, ChevronUp, Loader2 } from "lucide-react";
import { useStageDurations } from "@/lib/hooks/use-lead-v2";

interface Props {
  leadId: string;
  // Authoritative days-on-current-stage from LeadOut (read path). Falls
  // back to the per-stage `days` from the durations endpoint if absent.
  currentStageDays?: number | null;
}

type StageStatus = "done" | "current" | "pending";

/**
 * Stage progress for the LeadCard header.
 *
 * Default = COLLAPSED context view: previous stage · CURRENT (large,
 * with days) · next 1–2 stages, then a «показать все этапы» link.
 * Expanded = the full horizontal scrollable row with every stage.
 */
export function StagesStepper({ leadId, currentStageDays }: Props) {
  const { data: stages, isLoading, isError } = useStageDurations(leadId);
  const [expanded, setExpanded] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-2 type-caption text-brand-muted">
        <Loader2 size={11} className="animate-spin" />
        Загрузка этапов…
      </div>
    );
  }
  if (isError || !stages || stages.length === 0) return null;

  const currentIdx = stages.findIndex((s) => s.status === "current");

  // No current stage (won/lost/detached) — just show the full row.
  if (expanded || currentIdx === -1) {
    return (
      <div className="relative">
        {currentIdx !== -1 && (
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="absolute top-0 right-0 z-10 inline-flex items-center gap-1 px-2.5 py-1 rounded-full type-caption font-semibold bg-white border border-brand-border text-brand-muted hover:text-brand-primary hover:border-brand-accent transition-colors"
          >
            <ChevronUp size={11} /> свернуть
          </button>
        )}
        <FullRow stages={stages} />
      </div>
    );
  }

  // Collapsed context window: prev · current · next · next+1
  const windowItems = [
    currentIdx - 1,
    currentIdx,
    currentIdx + 1,
    currentIdx + 2,
  ]
    .filter((i) => i >= 0 && i < stages.length)
    .map((i) => stages[i]);

  const remaining = stages.length - (currentIdx + 3);
  const curDays =
    currentStageDays != null ? currentStageDays : stages[currentIdx].days;

  return (
    <div className="flex items-end flex-wrap gap-x-1 gap-y-2">
      {windowItems.map((s, idx) => {
        const isCurrent = s.status === "current";
        const isLast = idx === windowItems.length - 1;
        return (
          <div key={s.stage_id} className="flex items-end">
            <div
              className={`flex flex-col items-center ${
                isCurrent ? "w-[132px]" : "w-[92px]"
              }`}
            >
              <Dot status={s.status as StageStatus} large={isCurrent} />
              <p
                className={`mt-1.5 text-center px-1 truncate w-full ${
                  isCurrent
                    ? "type-label font-semibold text-brand-accent-text"
                    : "type-caption text-brand-muted"
                }`}
                title={s.stage_name}
              >
                {s.stage_name}
              </p>
              {isCurrent && curDays != null && (
                <p className="type-caption font-semibold text-brand-accent-text mt-0.5">
                  {curDays} {pluralDays(curDays)}
                </p>
              )}
            </div>
            {!isLast && (
              <div className="mb-6 h-px w-5 bg-brand-border" aria-hidden="true" />
            )}
          </div>
        );
      })}

      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="mb-6 ml-1 type-caption font-semibold text-brand-accent-text hover:underline whitespace-nowrap"
      >
        {remaining > 0 ? `ещё ${remaining} →` : "показать все этапы"}
      </button>
    </div>
  );
}

// Full scrollable row — every stage with its days.
function FullRow({
  stages,
}: {
  stages: {
    stage_id: string;
    stage_name: string;
    days: number | null;
    status: string;
  }[];
}) {
  return (
    <div className="overflow-x-auto -mx-2 px-2">
      <ol className="flex items-start gap-0 min-w-max">
        {stages.map((s, i) => {
          const isLast = i === stages.length - 1;
          const isDone = s.status === "done";
          const isCurrent = s.status === "current";
          return (
            <li key={s.stage_id} className="flex items-start">
              <div className="flex flex-col items-center w-[120px] shrink-0">
                <Dot status={s.status as StageStatus} />
                <p
                  className={`mt-1.5 type-caption text-center px-1 truncate w-full ${
                    isCurrent
                      ? "font-semibold text-brand-accent-text"
                      : isDone
                        ? "text-brand-primary"
                        : "text-brand-muted"
                  }`}
                  title={s.stage_name}
                >
                  {s.stage_name}
                </p>
                {s.days != null && (
                  <p
                    className={
                      isCurrent
                        ? "type-body font-semibold text-brand-accent-text mt-0.5"
                        : "text-[10px] text-brand-muted mt-0.5"
                    }
                  >
                    {s.days} {pluralDays(s.days)}
                  </p>
                )}
              </div>
              {!isLast && (
                <div
                  className={`mt-3 h-px w-8 ${
                    isDone ? "bg-success/60" : "bg-brand-border"
                  }`}
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Dot({ status, large }: { status: StageStatus; large?: boolean }) {
  const size = large ? "w-8 h-8" : "w-6 h-6";
  if (status === "done") {
    return (
      <span
        className={`${size} rounded-full bg-success text-white flex items-center justify-center shrink-0`}
      >
        <Check size={large ? 14 : 12} strokeWidth={3} />
      </span>
    );
  }
  if (status === "current") {
    return (
      <span
        className={`${size} rounded-full bg-brand-accent text-white flex items-center justify-center shrink-0`}
        style={{ boxShadow: "0 0 0 4px rgba(255, 78, 0, 0.18)" }}
        aria-current="step"
      >
        <span className="w-2 h-2 rounded-full bg-white" />
      </span>
    );
  }
  return (
    <span
      className={`${size} rounded-full bg-white border border-brand-border shrink-0`}
    />
  );
}

function pluralDays(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "дня";
  return "дней";
}
