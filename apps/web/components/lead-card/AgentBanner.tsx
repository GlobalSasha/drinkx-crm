"use client";

// Sprint 3.1 Phase D — Background-mode banner inside the LeadCard.
//
// Renders a single recommendation card between the LeadCard header
// and the tab strip. The recommendation is whatever the runner
// last wrote into `lead.agent_state['suggestion']` (cheap GET,
// no LLM call); a manual «Обновить» button enqueues a Celery
// refresh that overwrites the slot when it lands.
//
// Design rules from the agent skill (`docs/skills/lead-ai-agent-skill.md`):
//   - Don't render when the runner returned `null` (== silent).
//   - `confidence < 0.4` is the «низкая уверенность» branch — we
//     muted the banner and dropped the `action_label` (server
//     enforces this clear too, so the UI just visualises it).
//   - The dismiss button removes the banner from the local view
//     for the rest of the session; the next refresh writes a
//     fresh suggestion that pops it back. (Persistent dismissals
//     ship in Phase 3.2 once we have a per-suggestion id.)

import { useState } from "react";
import { Bot, RefreshCw, Sparkles, X } from "lucide-react";

import {
  useAgentSuggestion,
  useRefreshAgentSuggestion,
} from "@/lib/hooks/use-lead-agent";
import { C } from "@/lib/design-system";


export function AgentBanner({
  leadId,
  onCoachOpen,
}: {
  leadId: string;
  onCoachOpen: () => void;
}) {
  const query = useAgentSuggestion(leadId);
  const refresh = useRefreshAgentSuggestion(leadId);
  const [dismissed, setDismissed] = useState(false);

  const suggestion = query.data?.suggestion ?? null;
  const isLoading = query.isLoading;

  // Empty-row state: never had a suggestion computed for this lead.
  // Render a thin «запросить рекомендацию» strip — clearer than
  // hiding the affordance entirely. Once the operator clicks
  // refresh and the backend writes a row, the full banner takes over.
  if (!suggestion && !isLoading) {
    if (dismissed) return null;
    return (
      <div className="border-y border-brand-border bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-2 flex items-center gap-3">
          <Bot size={14} className="text-brand-muted shrink-0" />
          <span className="type-caption text-brand-muted flex-1 min-w-0 truncate">
            Чак ещё не давал рекомендаций по этому лиду.
          </span>
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="inline-flex items-center gap-1 type-caption font-semibold text-brand-accent-text hover:opacity-80 transition disabled:opacity-50"
          >
            <RefreshCw
              size={12}
              className={refresh.isPending ? "animate-spin" : ""}
            />
            {refresh.isPending ? "Запрос..." : "Запросить"}
          </button>
        </div>
      </div>
    );
  }

  // Dismissed in this session — re-shows on a manual refresh
  // (mutation invalidates the cache and re-fetches a fresh row).
  if (dismissed) return null;
  if (!suggestion) return null;  // loading; FollowupsRail covers the rest

  // Low-confidence branch: muted styling, no primary CTA — the
  // server already nulled `action_label`, but we keep the prop
  // check defensive.
  const lowConfidence = suggestion.confidence < 0.4;
  const primaryAction =
    !lowConfidence && suggestion.action_label
      ? suggestion.action_label
      : null;

  return (
    <div
      className={`border-y border-brand-border ${
        lowConfidence ? "bg-brand-bg" : "bg-brand-soft/40"
      }`}
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-start gap-3">
        <div className="pt-0.5">
          <Sparkles
            size={16}
            className={
              lowConfidence ? "text-brand-muted" : "text-brand-accent-text"
            }
          />
        </div>
        <div className="flex-1 min-w-0">
          <p className="type-caption text-brand-primary leading-snug">
            {suggestion.text}
          </p>
          <div className="flex items-center gap-3 mt-1.5 flex-wrap">
            {primaryAction && (
              <button
                type="button"
                onClick={onCoachOpen}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-accent text-white type-caption font-semibold hover:opacity-90 transition"
              >
                {primaryAction}
              </button>
            )}
            <button
              type="button"
              onClick={onCoachOpen}
              className="type-caption font-medium text-brand-accent-text hover:opacity-80 transition"
            >
              Спросить Чака →
            </button>
            <button
              type="button"
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
              className="inline-flex items-center gap-1 type-caption text-brand-muted hover:text-brand-primary transition disabled:opacity-50"
              title="Пересчитать рекомендацию"
            >
              <RefreshCw
                size={11}
                className={refresh.isPending ? "animate-spin" : ""}
              />
              {refresh.isPending ? "Обновляю" : "Обновить"}
            </button>
            <span className="type-caption text-brand-muted">
              · уверенность {Math.round(suggestion.confidence * 100)}%
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="text-brand-muted hover:text-brand-primary p-1 -m-1 shrink-0"
          aria-label="Скрыть рекомендацию"
          title="Скрыть"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
