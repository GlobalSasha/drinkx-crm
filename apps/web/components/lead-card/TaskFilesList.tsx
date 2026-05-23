"use client";

import {
  Download,
  FileAudio,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
  Trash2,
} from "lucide-react";
import {
  useDeleteTaskFile,
  useDownloadTaskFile,
  useTaskFiles,
} from "@/lib/hooks/use-task-files";

function kindIcon(kind: string | null) {
  switch (kind) {
    case "image":
      return <ImageIcon size={14} />;
    case "audio":
      return <FileAudio size={14} />;
    case "spreadsheet":
      return <FileSpreadsheet size={14} />;
    default:
      return <FileText size={14} />;
  }
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

interface Props {
  leadId: string;
  taskId: string;
  q?: string;
}

export function TaskFilesList({ leadId, taskId, q }: Props) {
  const list = useTaskFiles(leadId, taskId, q);
  const download = useDownloadTaskFile();
  const remove = useDeleteTaskFile(leadId, taskId);

  if (list.isLoading) {
    return <p className="type-caption text-brand-muted">Загрузка…</p>;
  }
  const files = list.data ?? [];
  if (files.length === 0) {
    return <p className="type-caption text-brand-muted italic">Файлов нет</p>;
  }

  async function open(activityId: string) {
    try {
      const { url } = await download.mutateAsync(activityId);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      /* mutation state surfaces the error; nothing to do here */
    }
  }

  function handleRemove(activityId: string, fileName: string) {
    // Per-file deletes are infrequent; an inline two-step would clutter the dense list.
    // Lead-level destructive ops have a dedicated modal; one file is replaceable by re-upload.
    if (window.confirm(`Удалить файл «${fileName}»?`)) {
      remove.mutate(activityId);
    }
  }

  return (
    <ul className="flex flex-col gap-1.5">
      {files.map((f) => (
        <li
          key={f.id}
          className="flex items-center gap-2 px-3 py-2 rounded-2xl bg-brand-bg"
        >
          <span className="text-brand-muted shrink-0">{kindIcon(f.file_kind)}</span>
          <div className="flex-1 min-w-0">
            <p className="type-body text-brand-primary truncate">{f.file_name}</p>
            <p className="type-caption text-brand-muted">
              {fmtSize(f.file_size)}
              {f.body ? ` · ${f.body}` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={() => open(f.id)}
            disabled={download.isPending}
            aria-label="Скачать"
            className="shrink-0 text-brand-muted hover:text-brand-accent disabled:opacity-40"
          >
            <Download size={14} />
          </button>
          <button
            type="button"
            onClick={() => handleRemove(f.id, f.file_name)}
            disabled={remove.isPending}
            aria-label="Удалить файл"
            className="shrink-0 text-rose/70 hover:text-rose disabled:opacity-40"
          >
            <Trash2 size={14} />
          </button>
        </li>
      ))}
    </ul>
  );
}
