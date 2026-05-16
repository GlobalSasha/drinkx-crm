"use client";

import { ExternalLink, Mail, Paperclip } from "lucide-react";
import type { FeedItemOut } from "@/lib/types";
import { formatDateShort, formatTimeShort } from "./_time";

interface Props {
  item: FeedItemOut;
  onOpen: () => void;
}

export function FeedItemEmail({ item, onOpen }: Props) {
  const subject = item.subject || "Без темы";
  const from = item.from_identifier || "—";
  const to = item.to_identifier || "—";
  // Attachments live inside payload_json — Gmail ingest stamps a count.
  const attachmentsRaw = item.payload_json?.attachments;
  const attachmentsCount = Array.isArray(attachmentsRaw)
    ? attachmentsRaw.length
    : (item.payload_json?.has_attachments ? 1 : 0);

  return (
    <div className="flex gap-3 group">
      <div className="shrink-0 w-7 h-7 rounded-full bg-brand-panel flex items-center justify-center">
        <Mail size={13} className="text-brand-muted-strong" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="type-caption text-brand-muted">
          <span className="font-semibold text-brand-primary">Письмо</span>
          <span className="mx-1.5">·</span>
          <span>
            {formatDateShort(item.created_at)}, {formatTimeShort(item.created_at)}
          </span>
        </p>

        <button
          type="button"
          onClick={onOpen}
          className="mt-1 w-full text-left rounded-2xl border border-brand-border bg-white p-3 hover:border-brand-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
        >
          <div className="flex items-start justify-between gap-2 mb-1.5">
            <p className="type-caption text-brand-muted truncate">
              От: <span className="text-brand-primary">{from}</span>
              <span className="mx-1">→</span>
              <span className="text-brand-primary">{to}</span>
            </p>
            <span className="inline-flex items-center gap-1 type-caption text-brand-accent-text shrink-0">
              Открыть <ExternalLink size={11} />
            </span>
          </div>
          <p className="type-body font-semibold text-brand-primary truncate">
            {subject}
          </p>
          {attachmentsCount > 0 && (
            <p className="inline-flex items-center gap-1 mt-1 type-caption text-brand-muted">
              <Paperclip size={11} />
              Вложений: {attachmentsCount}
            </p>
          )}
        </button>
      </div>
    </div>
  );
}
