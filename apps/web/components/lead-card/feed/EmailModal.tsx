"use client";

import { Mail, Paperclip } from "lucide-react";
import type { FeedItemOut } from "@/lib/types";
import { Modal } from "@/components/ui/Modal";
import { formatDateShort, formatTimeShort } from "./_time";

interface Props {
  item: FeedItemOut;
  onClose: () => void;
}

export function EmailModal({ item, onClose }: Props) {
  const subject = item.subject || "Без темы";
  const attachmentsRaw = item.payload_json?.attachments;
  const attachments: Array<{ filename?: string; url?: string }> =
    Array.isArray(attachmentsRaw) ? attachmentsRaw : [];

  return (
    <Modal open onClose={onClose} title={subject} size="max-w-2xl">
      <div className="-m-6">
        <header className="px-6 py-4 border-b border-brand-border">
          <div className="flex items-center gap-2 mb-2">
            <Mail size={14} className="text-brand-muted-strong" />
            <span className="type-caption text-brand-muted">
              {formatDateShort(item.created_at)}, {formatTimeShort(item.created_at)}
            </span>
          </div>
          <h3 className="type-card-title text-brand-primary mb-3">{subject}</h3>
          <dl className="grid grid-cols-[60px_1fr] gap-y-1 type-caption">
            <dt className="text-brand-muted">От:</dt>
            <dd className="text-brand-primary font-mono break-all">
              {item.from_identifier || "—"}
            </dd>
            <dt className="text-brand-muted">Кому:</dt>
            <dd className="text-brand-primary font-mono break-all">
              {item.to_identifier || "—"}
            </dd>
          </dl>
        </header>

        <div className="px-6 py-4 max-h-[60vh] overflow-y-auto">
          {item.body ? (
            <p className="type-body text-brand-primary whitespace-pre-wrap break-words">
              {item.body}
            </p>
          ) : (
            <p className="type-hint text-brand-muted">Пустое тело письма</p>
          )}
        </div>

        {attachments.length > 0 && (
          <footer className="px-6 py-4 border-t border-brand-border">
            <p className="type-caption font-semibold text-brand-muted-strong mb-2">
              Вложения
            </p>
            <ul className="space-y-1">
              {attachments.map((att, i) => (
                <li key={i}>
                  {att.url ? (
                    <a
                      href={att.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 type-caption text-brand-accent-text hover:underline"
                    >
                      <Paperclip size={11} />
                      {att.filename || `Вложение ${i + 1}`}
                    </a>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 type-caption text-brand-muted">
                      <Paperclip size={11} />
                      {att.filename || `Вложение ${i + 1}`}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </footer>
        )}
      </div>
    </Modal>
  );
}
