"use client";

import { Bot, Sparkles } from "lucide-react";
import type { FeedItemOut } from "@/lib/types";
import { formatTimeShort } from "./_time";

interface Props {
  item: FeedItemOut;
  /** Pre-fills the composer with «@Чак ...» for follow-up questions. */
  onAskFollowUp?: (seed: string) => void;
}

/**
 * AI suggestion / Чак's chat answer rendered as a native feed message.
 *
 * - Background: subtle brand-soft tint so AI messages stand out from
 *   manager comments without being loud.
 * - Action button: only when payload_json.action_label is present
 *   AND confidence ≥ 0.4 (server already strips action_label below
 *   that threshold, so this is mostly defensive on the client).
 * - "Спросить подробнее" fires the parent callback with an empty seed
 *   so the composer focuses with the "@Чак " prefix.
 */
export function FeedItemAI({ item, onAskFollowUp }: Props) {
  const actionLabel = item.payload_json?.action_label as string | null | undefined;
  const confidence = item.payload_json?.confidence as number | null | undefined;
  const showAction =
    !!actionLabel && typeof confidence === "number" && confidence >= 0.4;

  return (
    <div className="flex gap-3 group">
      <div className="shrink-0 w-7 h-7 rounded-full bg-brand-accent flex items-center justify-center">
        <Bot size={13} className="text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="type-caption text-brand-muted">
          <span className="font-semibold text-brand-accent-text">Чак</span>
          <span className="mx-1.5">·</span>
          <span>{formatTimeShort(item.created_at)}</span>
        </p>
        <div className="mt-1 rounded-2xl bg-brand-soft/40 border border-brand-soft p-3">
          {item.body && (
            <p className="type-body text-brand-primary whitespace-pre-wrap break-words">
              {item.body}
            </p>
          )}
          {(showAction || onAskFollowUp) && (
            <div className="flex flex-wrap items-center gap-2 mt-3">
              {showAction && (
                <button
                  type="button"
                  className="inline-flex items-center gap-1 px-3 py-1 type-caption font-semibold bg-brand-accent text-white rounded-full hover:bg-brand-accent/90 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                >
                  <Sparkles size={11} />
                  {actionLabel}
                </button>
              )}
              {onAskFollowUp && (
                <button
                  type="button"
                  onClick={() => onAskFollowUp("")}
                  className="inline-flex items-center px-3 py-1 type-caption font-semibold text-brand-accent-text hover:bg-brand-soft/60 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                >
                  Спросить подробнее
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
