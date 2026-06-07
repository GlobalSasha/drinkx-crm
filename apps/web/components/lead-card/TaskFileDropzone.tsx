"use client";

import { useRef, useState } from "react";
import { Loader2, Paperclip, X } from "lucide-react";
import { useUploadTaskFile } from "@/lib/hooks/use-task-files";

const ACCEPT =
  ".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.rtf,.png,.jpg,.jpeg,.gif,.webp,.heic,.mp3,.wav,.m4a,.ogg";
const MAX_MB = 25;

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

interface Props {
  leadId: string;
  taskId: string;
}

export function TaskFileDropzone({ leadId, taskId }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [picked, setPicked] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadTaskFile(leadId, taskId);

  function handlePick(file: File) {
    setError(null);
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`Слишком большой файл: ${fmtSize(file.size)} (лимит ${MAX_MB} МБ)`);
      return;
    }
    setPicked(file);
  }

  async function submit() {
    if (!picked || upload.isPending) return;
    setError(null);
    try {
      await upload.mutateAsync({ file: picked, caption: caption.trim() || undefined });
      setPicked(null);
      setCaption("");
    } catch (e) {
      setError((e as Error).message || "Не удалось загрузить");
    }
  }

  if (picked) {
    return (
      <div className="bg-brand-bg rounded-card p-3 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="type-caption text-brand-primary truncate">
            {picked.name} · {fmtSize(picked.size)}
          </span>
          <button
            type="button"
            onClick={() => {
              setPicked(null);
              setCaption("");
              setError(null);
            }}
            disabled={upload.isPending}
            aria-label="Отменить выбор"
            className="text-brand-muted hover:text-brand-primary disabled:opacity-40"
          >
            <X size={14} />
          </button>
        </div>
        <input
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          placeholder="Подпись (необязательно)"
          disabled={upload.isPending}
          className="w-full px-3 py-1.5 rounded-full bg-white border border-brand-border type-caption outline-none focus:border-brand-accent"
        />
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={submit}
            disabled={upload.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full type-caption font-semibold bg-brand-accent text-white hover:bg-brand-accent/90 disabled:opacity-40"
          >
            {upload.isPending && <Loader2 size={12} className="animate-spin" />}
            Загрузить
          </button>
          {error && <span className="type-caption text-rose">{error}</span>}
        </div>
      </div>
    );
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) handlePick(f);
      }}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer rounded-card border-2 border-dashed p-3 text-center transition-colors ${
        dragOver
          ? "border-brand-accent bg-brand-soft"
          : "border-brand-border bg-white hover:border-brand-accent"
      }`}
    >
      <div className="inline-flex items-center gap-1.5 type-caption text-brand-muted">
        <Paperclip size={14} />
        Перетащите файл или нажмите, чтобы прикрепить
      </div>
      <p className="type-caption text-brand-muted mt-1">
        До {MAX_MB} МБ · pdf / image / xlsx / doc / txt / audio
      </p>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handlePick(f);
          e.target.value = ""; // allow re-selecting the same file
        }}
      />
      {error && <p className="type-caption text-rose mt-1">{error}</p>}
    </div>
  );
}
