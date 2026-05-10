"use client";
import { useState } from "react";
import { Sparkles, X, RefreshCw, Loader2 } from "lucide-react";
import {
  useAgentSuggestion,
  useRefreshSuggestion,
} from "@/lib/hooks/use-lead-agent";
import { C } from "@/lib/design-system";

interface Props {
  leadId: string;
  /** Called when the action button is clicked — the parent typically
   *  opens the Sales Coach drawer to continue the conversation. */
  onAction?: () => void;
}

/**
 * Lead AI Agent banner (Sprint 3.1 Phase D).
 *
 * Slot: between the LeadCard sticky header and the tab strip. Shows
 * the cached `agent_state.suggestion`. Hidden when there is no
 * suggestion, when the user dismissed it for this session, or while
 * the initial query is loading.
 *
 * Dismissal is session-local (no backend «manager_action» field in
 * the simplified Phase C schema). The next refresh from the user or
 * the `scan_silence` cron writes a fresh suggestion which un-hides
 * the banner via React Query cache.
 */
export function AgentBanner({ leadId, onAction }: Props) {
  const { data, isLoading, isError } = useAgentSuggestion(leadId);
  const refresh = useRefreshSuggestion(leadId);
  const [dismissed, setDismissed] = useState(false);

  if (isLoading || isError) return null;
  const suggestion = data?.suggestion ?? null;
  if (!suggestion) return null;
  if (dismissed) return null;

  const showAction = !!suggestion.action_label && suggestion.confidence >= 0.4;

  return (
    <div className="bg-brand-soft border border-brand-accent/20 rounded-2xl p-4 mb-4">
      <div className="flex items-start gap-3">
        <Sparkles
          size={16}
          className="text-brand-accent-text shrink-0 mt-0.5"
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <p
            className={`${C.bodyXs} ${C.color.mutedLight} uppercase tracking-wide mb-1`}
          >
            рекомендация чака
          </p>
          <p className={`${C.bodySm} ${C.color.text} leading-snug`}>
            {suggestion.text}
          </p>
          {(showAction || refresh.isPending) && (
            <div className="flex items-center gap-2 mt-3">
              {showAction && (
                <button
                  onClick={onAction}
                  className={`${C.button.primary} ${C.btn} px-3 py-1.5`}
                >
                  {suggestion.action_label}
                </button>
              )}
              {refresh.isPending && (
                <span
                  className={`flex items-center gap-1 ${C.bodyXs} ${C.color.mutedLight}`}
                >
                  <Loader2 size={12} className="animate-spin" aria-hidden />
                  обновляю…
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            title="Пересчитать"
            aria-label="Пересчитать рекомендацию"
            className={`p-1.5 rounded-full ${C.color.mutedLight} disabled:opacity-40`}
          >
            <RefreshCw size={13} aria-hidden />
          </button>
          <button
            onClick={() => setDismissed(true)}
            title="Скрыть"
            aria-label="Скрыть баннер"
            className={`p-1.5 rounded-full ${C.color.mutedLight}`}
          >
            <X size={13} aria-hidden />
          </button>
        </div>
      </div>
    </div>
  );
}
