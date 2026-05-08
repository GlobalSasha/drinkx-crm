"use client";

import { useCallback, useRef, useState } from "react";
import { AlertCircle, FileText, Loader2, Upload } from "lucide-react";
import { clsx } from "clsx";

import { useUploadImport } from "@/lib/hooks/use-import";
import { ApiError } from "@/lib/api-client";
import type { ImportJobOut } from "@/lib/types";

const ACCEPTED_EXT = [".xlsx", ".csv", ".json", ".yaml", ".yml"] as const;
const ACCEPT_ATTR = ACCEPTED_EXT.join(",");
const MAX_MB = 10;

interface Props {
  onUploaded: (job: ImportJobOut) => void;
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

export function UploadStep({ onUploaded }: Props) {
  const [picked, setPicked] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadImport();

  const handlePick = useCallback((file: File) => {
    setError(null);
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`Файл слишком большой: ${fmtSize(file.size)}. Лимит: ${MAX_MB} МБ.`);
      return;
    }
    setPicked(file);
  }, []);

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handlePick(f);
    // reset value so picking the same file twice still fires onChange
    e.target.value = "";
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handlePick(f);
  }

  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    if (!dragOver) setDragOver(true);
  }

  function onDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
  }

  function startUpload() {
    if (!picked) return;
    setError(null);
    upload.mutate(picked, {
      onSuccess: onUploaded,
      onError: (err) => {
        const message =
          err instanceof ApiError
            ? typeof err.body === "object" && err.body && "detail" in err.body
              ? String((err.body as { detail?: unknown }).detail)
              : `Ошибка ${err.status}`
            : "Не удалось загрузить файл";
        setError(message);
        setPicked(null);
      },
    });
  }

  const busy = upload.isPending;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-extrabold tracking-tight text-ink">
          Загрузите файл
        </h3>
        <p className="text-[13px] text-muted mt-1">
          Поддерживаются Excel, CSV, JSON, YAML — до {MAX_MB} МБ.
        </p>
      </div>

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        disabled={busy}
        className={clsx(
          "w-full rounded-2xl border-2 border-dashed transition-all duration-200 px-6 py-12 text-center flex flex-col items-center justify-center gap-3 outline-none",
          dragOver
            ? "border-accent bg-accent/5"
            : picked
              ? "border-emerald-400/40 bg-emerald-50/40"
              : "border-black/15 hover:border-accent/60 hover:bg-canvas/60",
          busy && "opacity-60 cursor-wait",
        )}
      >
        {picked ? (
          <>
            <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 text-emerald-700 flex items-center justify-center">
              <FileText size={22} />
            </div>
            <div>
              <div className="text-sm font-bold text-ink">{picked.name}</div>
              <div className="text-[11px] font-mono text-muted-3 mt-0.5">
                {fmtSize(picked.size)}
              </div>
            </div>
            <div className="text-[11px] text-muted-2">
              Нажмите чтобы выбрать другой файл
            </div>
          </>
        ) : (
          <>
            <div
              className={clsx(
                "w-12 h-12 rounded-2xl flex items-center justify-center transition-colors",
                dragOver
                  ? "bg-accent text-white"
                  : "bg-canvas text-muted",
              )}
            >
              <Upload size={22} />
            </div>
            <div>
              <div className="text-sm font-bold text-ink">
                Перетащите файл сюда
              </div>
              <div className="text-[12px] text-muted mt-0.5">
                или нажмите чтобы выбрать
              </div>
            </div>
            <div className="flex flex-wrap gap-1 justify-center mt-1">
              {ACCEPTED_EXT.filter((e) => e !== ".yml").map((ext) => (
                <span
                  key={ext}
                  className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-pill bg-black/5 text-muted-2"
                >
                  {ext}
                </span>
              ))}
            </div>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTR}
          className="sr-only"
          onChange={onInputChange}
          disabled={busy}
        />
      </button>

      {error && (
        <div className="flex items-start gap-2 text-[13px] text-red-700 bg-red-50 rounded-xl px-3 py-2.5">
          <AlertCircle size={14} className="shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex justify-end pt-2">
        <button
          onClick={startUpload}
          disabled={!picked || busy}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-pill bg-ink text-white text-sm font-semibold hover:bg-ink/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-300"
        >
          {busy && <Loader2 size={14} className="animate-spin" />}
          {busy ? "Загружаем и анализируем…" : "Продолжить"}
        </button>
      </div>
    </div>
  );
}
