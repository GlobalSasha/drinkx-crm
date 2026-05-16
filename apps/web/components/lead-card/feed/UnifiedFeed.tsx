"use client";

import { Fragment, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { useFeed } from "@/lib/hooks/use-feed";
import type { FeedItemOut } from "@/lib/types";
import { dayKey, formatDayHeader } from "./_time";
import { FeedItemAI } from "./FeedItemAI";
import { FeedItemCall } from "./FeedItemCall";
import { FeedItemComment } from "./FeedItemComment";
import { FeedItemEmail } from "./FeedItemEmail";
import { FeedItemSystem } from "./FeedItemSystem";
import { FeedItemTask } from "./FeedItemTask";
import { FeedComposer } from "./FeedComposer";
import { EmailModal } from "./EmailModal";
import { NextStepBanner } from "./NextStepBanner";

interface Props {
  leadId: string;
}

const SYSTEM_TYPES = new Set([
  "system",
  "stage_change",
  "score_update",
  "form_submission",
  "lead_assigned",
  "enrichment_done",
]);

/**
 * Main container for the unified activity feed. Renders date
 * separators between days, dispatches each item to its per-type
 * component, owns the email-modal + composer-seed state.
 */
export function UnifiedFeed({ leadId }: Props) {
  const feed = useFeed(leadId);
  const [openEmail, setOpenEmail] = useState<FeedItemOut | null>(null);
  const [composerSeed, setComposerSeed] = useState<string | undefined>(undefined);

  // Flatten the paged feed into one chronological list.
  const items = useMemo(() => {
    if (!feed.data) return [] as FeedItemOut[];
    return feed.data.pages.flatMap((p) => p.items);
  }, [feed.data]);

  if (feed.isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 type-caption text-brand-muted">
        <Loader2 size={14} className="animate-spin" />
        Загрузка ленты…
      </div>
    );
  }
  if (feed.isError) {
    return (
      <div className="py-6 type-caption text-rose">
        Не удалось загрузить ленту. Обнови страницу.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <NextStepBanner items={items} />

      <div className="space-y-3">
        {items.length === 0 && (
          <p className="type-hint text-brand-muted py-4 text-center">
            Лента пуста. Оставьте первый комментарий или задачу ниже.
          </p>
        )}

        {items.map((item, idx) => {
          const prev = idx > 0 ? items[idx - 1] : null;
          const showHeader = !prev || dayKey(prev.created_at) !== dayKey(item.created_at);
          return (
            <Fragment key={item.id}>
              {showHeader && (
                <div className="flex items-center gap-2 pt-2 pb-1">
                  <span className="type-caption font-semibold uppercase tracking-wide text-brand-muted">
                    {formatDayHeader(item.created_at)}
                  </span>
                  <div className="flex-1 h-px bg-brand-border" />
                </div>
              )}
              <div id={`activity-${item.id}`} className="scroll-mt-20">
                <FeedItemSwitch
                  item={item}
                  leadId={leadId}
                  onOpenEmail={setOpenEmail}
                  onAskFollowUp={(seed) => setComposerSeed(seed)}
                />
              </div>
            </Fragment>
          );
        })}

        {feed.hasNextPage && (
          <div className="pt-2 text-center">
            <button
              type="button"
              onClick={() => feed.fetchNextPage()}
              disabled={feed.isFetchingNextPage}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 type-caption font-semibold text-brand-muted hover:text-brand-primary bg-brand-bg hover:bg-brand-panel rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 disabled:opacity-50"
            >
              {feed.isFetchingNextPage && <Loader2 size={11} className="animate-spin" />}
              Показать ещё
            </button>
          </div>
        )}
      </div>

      <FeedComposer
        leadId={leadId}
        seed={composerSeed}
        onSeedConsumed={() => setComposerSeed(undefined)}
      />

      {openEmail && (
        <EmailModal item={openEmail} onClose={() => setOpenEmail(null)} />
      )}
    </div>
  );
}

function FeedItemSwitch({
  item,
  leadId,
  onOpenEmail,
  onAskFollowUp,
}: {
  item: FeedItemOut;
  leadId: string;
  onOpenEmail: (item: FeedItemOut) => void;
  onAskFollowUp: (seed: string) => void;
}) {
  if (SYSTEM_TYPES.has(item.type)) return <FeedItemSystem item={item} />;
  switch (item.type) {
    case "comment":
      return <FeedItemComment item={item} />;
    case "task":
      return <FeedItemTask item={item} leadId={leadId} />;
    case "phone":
      return <FeedItemCall item={item} />;
    case "email":
      return <FeedItemEmail item={item} onOpen={() => onOpenEmail(item)} />;
    case "ai_suggestion":
      return <FeedItemAI item={item} onAskFollowUp={onAskFollowUp} />;
    default:
      // Unknown types fall back to muted system row so a future
      // schema addition doesn't render as blank space.
      return <FeedItemSystem item={item} />;
  }
}
