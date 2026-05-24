"use client";

import {
  Download,
  FileAudio,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
  Paperclip,
  Trash2,
} from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useDownloadTaskFile } from "@/lib/hooks/use-task-files";
import { InlineConfirm } from "@/components/ui/InlineConfirm";
import type { FeedItemOut } from "@/lib/types";
import { formatTimeShort } from "./_time";

interface Props {
  item: FeedItemOut;
  leadId: string;
}

function kindIcon(kind: string | null | undefined) {
  switch (kind) {
    case "image":
      return <ImageIcon size={16} />;
    case "audio":
      return <FileAudio size={16} />;
    case "spreadsheet":
      return <FileSpreadsheet size={16} />;
    default:
      return <FileText size={16} />;
  }
}

function fmtSize(bytes: number | null | undefined): string {
  if (!bytes || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

/**
 * File activity in the lead feed — a real file uploaded via the
 * FeedComposer «Файл» mode. Shows a download tile with kind icon,
 * filename, size + caption, plus Download (opens 5-min signed URL)
 * and Delete actions. Mirrors the look of TaskFilesList rows so the
 * UX is consistent everywhere a file appears.
 */
export function FeedItemFile({ item, leadId }: Props) {
  const qc = useQueryClient();
  const download = useDownloadTaskFile();
  const remove = useMutation<void, Error, string>({
    mutationFn: (activityId) =>
      api.delete<void>(`/activities/${activityId}/file`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
      qc.invalidateQueries({ queryKey: ["task-files", leadId] });
    },
  });

  const author = item.author_name || "Менеджер";
  const payload = item.payload_json ?? {};
  const fileName =
    (payload.file_name as string | undefined) ?? item.file_url ?? "файл";
  const fileSize =
    (payload.file_size as number | undefined) ?? null;
  const fileKind = item.file_kind ?? (payload.file_kind as string | undefined) ?? null;
  const caption = item.body ?? null;

  async function open() {
    try {
      const { url } = await download.mutateAsync(item.id);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      /* surfaced via mutation state */
    }
  }

  return (
    <div className="flex gap-3 group">
      <div className="shrink-0 w-7 h-7 rounded-full bg-brand-panel flex items-center justify-center">
        <Paperclip size={13} className="text-brand-muted-strong" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <p className="type-caption text-brand-muted">
            <span className="font-semibold text-brand-primary">{author}</span>
            <span className="mx-1.5">·</span>
            <span>Файл</span>
            <span className="mx-1.5">·</span>
            <span>{formatTimeShort(item.created_at)}</span>
          </p>
        </div>

        <div className="mt-1 flex items-center gap-2 px-3 py-2.5 rounded-2xl bg-white border border-brand-border">
          <span className="text-brand-muted shrink-0">{kindIcon(fileKind)}</span>
          <div className="flex-1 min-w-0">
            <p className="type-body text-brand-primary truncate" title={fileName}>
              {fileName}
            </p>
            <p className="type-caption text-brand-muted">
              {fmtSize(fileSize)}
              {caption ? ` · ${caption}` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={open}
            disabled={download.isPending}
            aria-label="Скачать файл"
            className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-full text-brand-muted hover:text-brand-accent hover:bg-brand-bg disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
          >
            <Download size={14} />
          </button>
          <InlineConfirm
            destructive
            prompt={`Удалить «${fileName}»?`}
            confirmLabel="Удалить"
            busy={remove.isPending}
            onConfirm={() => remove.mutate(item.id)}
          >
            {(openConfirm) => (
              <button
                type="button"
                onClick={openConfirm}
                disabled={remove.isPending}
                aria-label="Удалить файл"
                className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-full text-rose/70 hover:text-rose hover:bg-rose/5 disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
              >
                <Trash2 size={14} />
              </button>
            )}
          </InlineConfirm>
        </div>
      </div>
    </div>
  );
}
