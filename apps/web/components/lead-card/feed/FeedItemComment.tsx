"use client";

import { MessageSquare } from "lucide-react";
import type { FeedItemOut } from "@/lib/types";
import { formatTimeShort } from "./_time";

interface Props {
  item: FeedItemOut;
}

export function FeedItemComment({ item }: Props) {
  const author = item.author_name || "Менеджер";
  return (
    <div className="flex gap-3 group">
      <div className="shrink-0 w-7 h-7 rounded-full bg-brand-panel flex items-center justify-center">
        <MessageSquare size={13} className="text-brand-muted-strong" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="type-caption text-brand-muted">
          <span className="font-semibold text-brand-primary">{author}</span>
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
