"use client";

import { Send } from "lucide-react";
import type { FeedItemOut } from "@/lib/types";
import { formatTimeShort } from "./_time";

interface Props {
  item: FeedItemOut;
}

const CHANNEL_LABEL: Record<string, string> = {
  telegram: "Telegram",
  max: "MAX",
};

/**
 * Telegram / MAX messenger entry in the unified feed. Inbound rows are
 * written by `app/inbox/message_services.receive` when a webhook matches
 * a lead; outbound rows are written by `send`. Before Sprint 3.5 these
 * Activity rows fell through to FeedItemSystem because no case matched —
 * the audit caught the resulting "empty feeds" symptom.
 */
export function FeedItemMessenger({ item }: Props) {
  const channelLabel = CHANNEL_LABEL[item.channel ?? ""] ?? "Сообщение";
  const direction = item.direction === "outbound" ? "Исходящее" : "Входящее";
  const author = item.author_name || (item.direction === "outbound" ? "Менеджер" : "Клиент");

  return (
    <div className="flex gap-3 group">
      <div className="shrink-0 w-7 h-7 rounded-full bg-brand-panel flex items-center justify-center">
        <Send size={13} className="text-brand-muted-strong" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="type-caption text-brand-muted">
          <span className="font-semibold text-brand-primary">{author}</span>
          <span className="mx-1.5">·</span>
          <span>{channelLabel}</span>
          <span className="mx-1.5">·</span>
          <span>{direction}</span>
          <span className="mx-1.5">·</span>
          <span>{formatTimeShort(item.created_at)}</span>
        </p>
        {item.body && (
          <p className="type-body text-brand-primary mt-1 whitespace-pre-wrap break-words">
            {item.body}
          </p>
        )}
      </div>
    </div>
  );
}
