"use client";

import { Check, Loader2 } from "lucide-react";
import { useStageDurations } from "@/lib/hooks/use-lead-v2";

interface Props {
  leadId: string;
}

/**
 * Horizontal stage progress for the LeadCard header. One dot per stage
 * in the lead's pipeline + days-per-stage label.
 *
 * - `done` — green check dot, "N дней" muted under name
 * - `current` — accent dot with glow, days shown in larger font
 * - `pending` — empty white dot with border, no days
 *
 * Pipelines wider than the viewport: container scrolls horizontally,
 * never wraps to a second row (spec).
 */
export function StagesStepper({ leadId }: Props) {
  const { data: stages, isLoading, isError } = useStageDurations(leadId);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-2 type-caption text-brand-muted">
        <Loader2 size={11} className="animate-spin" />
        Загрузка этапов…
      </div>
    );
  }
  if (isError || !stages || stages.length === 0) return null;

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
                <Dot status={s.status} />
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

function Dot({ status }: { status: "done" | "current" | "pending" }) {
  if (status === "done") {
    return (
      <span className="w-6 h-6 rounded-full bg-success text-white flex items-center justify-center shrink-0">
        <Check size={12} strokeWidth={3} />
      </span>
    );
  }
  if (status === "current") {
    return (
      <span
        className="w-6 h-6 rounded-full bg-brand-accent text-white flex items-center justify-center shrink-0"
        style={{ boxShadow: "0 0 0 4px rgba(255, 78, 0, 0.18)" }}
        aria-current="step"
      >
        <span className="w-2 h-2 rounded-full bg-white" />
      </span>
    );
  }
  return (
    <span className="w-6 h-6 rounded-full bg-white border border-brand-border shrink-0" />
  );
}

function pluralDays(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "дня";
  return "дней";
}
