"use client";
import { Loader2, X } from "lucide-react";

import { useAutomationRuns } from "@/lib/hooks/use-automations";
import type { AutomationOut, AutomationRunOut } from "@/lib/types";

import { RunRow } from "./RunRow";

// ---------------------------------------------------------------------------
// Run history drawer
// ---------------------------------------------------------------------------

export function RunsDrawer({
  automation,
  onClose,
}: {
  automation: AutomationOut;
  onClose: () => void;
}) {
  const runsQuery = useAutomationRuns(automation.id);
  const runs: AutomationRunOut[] = runsQuery.data ?? [];
  const isMultiStep =
    Array.isArray(automation.steps_json) && automation.steps_json.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/30">
      <aside className="bg-white h-full w-full max-w-md shadow-xl flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-brand-border">
          <div className="min-w-0">
            <h3 className="type-card-title truncate">
              История запусков
            </h3>
            <p className="text-xs text-brand-muted truncate">
              {automation.name}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-brand-muted hover:text-brand-primary p-1"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {runsQuery.isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={20} className="animate-spin text-brand-muted" />
            </div>
          ) : runs.length === 0 ? (
            <p className="text-sm text-brand-muted text-center py-12">
              Запусков пока не было.
            </p>
          ) : (
            <ul className="space-y-2">
              {runs.map((r) => (
                <RunRow key={r.id} run={r} expandable={isMultiStep} />
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
