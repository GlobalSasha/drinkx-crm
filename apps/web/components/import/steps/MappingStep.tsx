"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, Check, ChevronLeft, Loader2, Minus } from "lucide-react";
import { clsx } from "clsx";

import { useConfirmMapping } from "@/lib/hooks/use-import";
import { ApiError } from "@/lib/api-client";
import type { ImportFieldDef, ImportJobOut } from "@/lib/types";

const NONE_VALUE = "__none__"; // <select> can't have a literal null value

interface Props {
  job: ImportJobOut;
  onBack: () => void;
  onConfirmed: (job: ImportJobOut) => void;
}

export function MappingStep({ job, onBack, onConfirmed }: Props) {
  const diff = job.diff_json;
  const headers = diff?.headers ?? [];
  const previewRows = diff?.rows ?? [];
  const fieldCatalog = diff?.field_catalog ?? [];
  const suggested = diff?.suggested_mapping ?? {};

  const [mapping, setMapping] = useState<Record<string, string | null>>(
    () => {
      const initial: Record<string, string | null> = {};
      for (const h of headers) initial[h] = suggested[h] ?? null;
      return initial;
    },
  );
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirmMapping();

  // Compute which fields are duplicated across two columns — soft-block
  // continue with an inline warning.
  const duplicateFields = useMemo(() => {
    const seen = new Map<string, number>();
    for (const v of Object.values(mapping)) {
      if (!v) continue;
      seen.set(v, (seen.get(v) ?? 0) + 1);
    }
    return new Set([...seen.entries()].filter(([, n]) => n > 1).map(([k]) => k));
  }, [mapping]);

  const requiredFields = fieldCatalog.filter((f) => f.required);
  const mappedKeys = new Set(Object.values(mapping).filter(Boolean) as string[]);
  const missingRequired = requiredFields.filter((f) => !mappedKeys.has(f.key));

  const canSubmit =
    !confirm.isPending &&
    missingRequired.length === 0 &&
    duplicateFields.size === 0;

  function getSamplePreview(header: string): string {
    for (const row of previewRows) {
      const v = row[header];
      if (v && v.trim()) return v.length > 60 ? v.slice(0, 60) + "…" : v;
    }
    return "";
  }

  function setHeader(header: string, value: string) {
    setMapping((m) => ({
      ...m,
      [header]: value === NONE_VALUE ? null : value,
    }));
  }

  function submit() {
    setError(null);
    // Send only the assigned headers — backend treats missing as null too
    // but we keep the wire payload tight.
    const payload: Record<string, string | null> = {};
    for (const [h, v] of Object.entries(mapping)) {
      if (v) payload[h] = v;
    }
    confirm.mutate(
      { id: job.id, mapping: payload },
      {
        onSuccess: onConfirmed,
        onError: (err) => {
          const detail =
            err instanceof ApiError && typeof err.body === "object" && err.body
              ? (err.body as { detail?: unknown }).detail
              : null;
          setError(detail ? String(detail) : "Не удалось сохранить маппинг");
        },
      },
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-extrabold tracking-tight text-ink">
          Сопоставьте колонки
        </h3>
        <p className="text-[13px] text-muted mt-1">
          Подсказали что смогли. Поправьте где не совпадает или поставьте «не
          импортировать».
        </p>
      </div>

      {/* Required-field banner */}
      {missingRequired.length > 0 && (
        <div className="flex items-start gap-2 text-[13px] text-amber-800 bg-amber-50 rounded-xl px-3 py-2.5">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span>
            Обязательно нужно сопоставить:{" "}
            <span className="font-semibold">
              {missingRequired.map((f) => f.label_ru).join(", ")}
            </span>
            .
          </span>
        </div>
      )}

      {/* Duplicate-field banner */}
      {duplicateFields.size > 0 && (
        <div className="flex items-start gap-2 text-[13px] text-amber-800 bg-amber-50 rounded-xl px-3 py-2.5">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span>
            Одно поле CRM сопоставлено с несколькими колонками. Уберите дубли
            чтобы продолжить.
          </span>
        </div>
      )}

      {/* Mapping table */}
      <div className="rounded-2xl border border-black/5 bg-white overflow-hidden">
        <div className="grid grid-cols-[1fr_1fr_minmax(180px,1.2fr)_24px] items-center gap-3 px-4 py-2.5 bg-canvas border-b border-black/5 text-[10px] font-mono uppercase tracking-wider text-muted-2">
          <span>Колонка в файле</span>
          <span className="hidden md:block">Пример значения</span>
          <span>Поле CRM</span>
          <span />
        </div>
        <div className="divide-y divide-black/5 max-h-[42vh] overflow-y-auto">
          {headers.map((header) => {
            const current = mapping[header];
            const isDuplicate = current && duplicateFields.has(current);
            const sample = getSamplePreview(header);
            return (
              <div
                key={header}
                className="grid grid-cols-[1fr_1fr_minmax(180px,1.2fr)_24px] items-center gap-3 px-4 py-3"
              >
                <span className="text-sm font-semibold text-ink truncate">
                  {header}
                </span>
                <span className="hidden md:block text-[12px] font-mono text-muted-3 truncate">
                  {sample || "—"}
                </span>
                <select
                  value={current ?? NONE_VALUE}
                  onChange={(e) => setHeader(header, e.target.value)}
                  className={clsx(
                    "text-sm bg-canvas border rounded-lg px-2.5 py-1.5 outline-none transition-colors w-full",
                    isDuplicate
                      ? "border-amber-400 focus:border-amber-500"
                      : "border-black/10 focus:border-accent",
                  )}
                >
                  <option value={NONE_VALUE}>— не импортировать</option>
                  {fieldCatalog.map((f) => (
                    <option key={f.key} value={f.key}>
                      {f.label_ru}
                      {f.required ? " *" : ""}
                    </option>
                  ))}
                </select>
                <span
                  className={clsx(
                    "flex items-center justify-center text-[11px] font-mono",
                    current && !isDuplicate
                      ? "text-emerald-600"
                      : "text-muted-3",
                  )}
                  aria-label={current ? "сопоставлено" : "не сопоставлено"}
                >
                  {current && !isDuplicate ? <Check size={14} /> : <Minus size={14} />}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="text-[13px] text-red-700 bg-red-50 rounded-xl px-3 py-2.5">
          {error}
        </div>
      )}

      <FieldHint catalog={fieldCatalog} />

      <div className="flex items-center justify-between pt-2">
        <button
          onClick={onBack}
          disabled={confirm.isPending}
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted hover:text-ink disabled:opacity-40 transition-colors"
        >
          <ChevronLeft size={14} />
          Назад
        </button>
        <button
          onClick={submit}
          disabled={!canSubmit}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-pill bg-ink text-white text-sm font-semibold hover:bg-ink/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-300"
        >
          {confirm.isPending && <Loader2 size={14} className="animate-spin" />}
          {confirm.isPending ? "Сохраняем…" : "Продолжить"}
        </button>
      </div>
    </div>
  );
}

function FieldHint({ catalog }: { catalog: ImportFieldDef[] }) {
  const required = catalog.filter((f) => f.required);
  if (required.length === 0) return null;
  return (
    <p className="text-[11px] text-muted-3">
      <span className="font-mono">*</span> — обязательное поле. Достаточно
      {required.length > 1 ? " их" : " его"} сопоставить, остальные
      опциональны.
    </p>
  );
}
