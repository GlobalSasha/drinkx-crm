"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";

import { T } from "@/lib/design-system";
import { useAutomationStepRuns } from "@/lib/hooks/use-automations";
import type { AutomationRunOut, AutomationStepType } from "@/lib/types";

import { StatusIcon } from "./StatusIcon";
import { StepStatusIcon } from "./StepStatusIcon";
import { RUN_STATUS_LABELS, STEP_RUN_STATUS_LABELS, STEP_TYPE_LABELS } from "./types";

// ---------------------------------------------------------------------------
// Run row — Sprint 2.7 G2: expandable per-step grid for multi-step chains.
// ---------------------------------------------------------------------------

export function RunRow({
  run,
  expandable,
}: {
  run: AutomationRunOut;
  expandable: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const stepsQuery = useAutomationStepRuns(expanded ? run.id : null);

  return (
    <li className="rounded-xl bg-brand-bg/60 border border-brand-border overflow-hidden">
      <button
        type="button"
        onClick={() => expandable && setExpanded((v) => !v)}
        disabled={!expandable}
        className="w-full flex items-start gap-2 px-3 py-2 text-left hover:bg-brand-bg/80 disabled:cursor-default"
      >
        <div className="pt-0.5">
          <StatusIcon status={run.status} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-brand-primary">
            {RUN_STATUS_LABELS[run.status]}
          </div>
          <div className={`${T.mono} text-brand-muted`}>
            {new Date(run.executed_at).toLocaleString("ru-RU")}
          </div>
          {run.error && (
            <p className="text-xs text-brand-muted mt-1 break-words">
              {run.error}
            </p>
          )}
        </div>
        {expandable && (
          <div className="pt-0.5 text-brand-muted">
            {expanded ? (
              <ChevronDown size={12} />
            ) : (
              <ChevronRight size={12} />
            )}
          </div>
        )}
      </button>

      {expanded && (
        <div className="border-t border-brand-border px-3 py-2 bg-white">
          {stepsQuery.isLoading ? (
            <div className="flex items-center gap-1.5 text-xs text-brand-muted py-1">
              <Loader2 size={10} className="animate-spin" /> Загрузка шагов...
            </div>
          ) : !stepsQuery.data || stepsQuery.data.length === 0 ? (
            <p className="text-xs text-brand-muted">Нет шагов для этого запуска.</p>
          ) : (
            <ul className="space-y-1">
              {stepsQuery.data.map((sr) => {
                const stepType =
                  (sr.step_json?.type as AutomationStepType) ?? "delay_hours";
                return (
                  <li
                    key={sr.id}
                    className="flex items-start gap-1.5 text-xs"
                  >
                    <div className="pt-0.5 w-3 text-brand-muted font-mono">
                      {sr.step_index + 1}
                    </div>
                    <div className="pt-0.5">
                      <StepStatusIcon status={sr.status} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium">
                        {STEP_TYPE_LABELS[stepType]}
                        <span className="ml-1.5 text-brand-muted">
                          · {STEP_RUN_STATUS_LABELS[sr.status]}
                        </span>
                      </div>
                      <div className={`${T.mono} text-brand-muted`}>
                        {sr.executed_at
                          ? `выполнен ${new Date(sr.executed_at).toLocaleString("ru-RU")}`
                          : `запланирован на ${new Date(sr.scheduled_at).toLocaleString("ru-RU")}`}
                      </div>
                      {sr.error && (
                        <p className="text-xs text-brand-muted mt-0.5 break-words">
                          {sr.error}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}
