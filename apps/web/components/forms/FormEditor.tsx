"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  Code2,
  Copy,
  Loader2,
  Plus,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import { clsx } from "clsx";

import { useCreateForm, useUpdateForm } from "@/lib/hooks/use-forms";
import { usePipelines } from "@/lib/hooks/use-pipelines";
import { ApiError } from "@/lib/api-client";
import type {
  FieldDefinition,
  FieldType,
  WebFormOut,
} from "@/lib/types";

type Tab = "settings" | "embed";

const FIELD_TYPES: { value: FieldType; label: string }[] = [
  { value: "text", label: "Текст" },
  { value: "email", label: "Почта" },
  { value: "phone", label: "Телефон" },
  { value: "textarea", label: "Многострочный текст" },
  { value: "select", label: "Выпадающий список" },
];

const DEFAULT_FIELDS: FieldDefinition[] = [
  { key: "company_name", label: "Название компании", type: "text", required: true },
  { key: "email", label: "Почта", type: "email", required: false },
  { key: "phone", label: "Телефон", type: "phone", required: false },
];

interface FieldRow extends FieldDefinition {
  // React key — survives add/delete without stable backend id
  _clientId: string;
}

function withClientIds(fields: FieldDefinition[]): FieldRow[] {
  return fields.map((f, i) => ({
    ...f,
    options: f.options ?? null,
    _clientId: `${Date.now()}-${i}-${Math.random().toString(36).slice(2, 6)}`,
  }));
}

function stripClientIds(rows: FieldRow[]): FieldDefinition[] {
  return rows.map(({ _clientId, ...rest }) => ({  // eslint-disable-line @typescript-eslint/no-unused-vars
    ...rest,
    options: rest.type === "select" ? rest.options ?? [] : undefined,
  }));
}

interface Props {
  open: boolean;
  form?: WebFormOut;
  onClose: () => void;
  onSaved: (form: WebFormOut) => void;
}

export function FormEditor({ open, form, onClose, onSaved }: Props) {
  const isEdit = !!form;
  const [tab, setTab] = useState<Tab>("settings");

  const [name, setName] = useState("");
  const [fields, setFields] = useState<FieldRow[]>([]);
  const [targetStageId, setTargetStageId] = useState<string | null>(null);
  const [targetPipelineId, setTargetPipelineId] = useState<string | null>(null);
  const [redirectUrl, setRedirectUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const create = useCreateForm();
  const update = useUpdateForm();
  const pipelinesQuery = usePipelines();

  // Reset state every time the editor opens — fresh form / fresh edits.
  useEffect(() => {
    if (!open) return;
    setError(null);
    setCopied(false);
    setTab("settings");
    if (form) {
      setName(form.name);
      setFields(withClientIds(form.fields_json || []));
      setTargetStageId(form.target_stage_id);
      setTargetPipelineId(form.target_pipeline_id);
      setRedirectUrl(form.redirect_url || "");
    } else {
      setName("");
      setFields(withClientIds(DEFAULT_FIELDS));
      setTargetStageId(null);
      setTargetPipelineId(null);
      setRedirectUrl("");
    }
  }, [open, form]);

  // Esc closes the modal — but not while a save is in flight, otherwise
  // the manager could close mid-mutation and miss the success/failure.
  const busy = create.isPending || update.isPending;
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  // Flatten {pipeline → stages} into a single list for the dropdown.
  // Most workspaces have one pipeline; this future-proofs without
  // adding a separate pipeline picker.
  const stageOptions = useMemo(() => {
    const out: { id: string; pipelineId: string; label: string }[] = [];
    for (const p of pipelinesQuery.data ?? []) {
      for (const s of p.stages || []) {
        out.push({
          id: s.id,
          pipelineId: p.id,
          label: `${p.name} → ${s.name}`,
        });
      }
    }
    return out;
  }, [pipelinesQuery.data]);

  if (!open) return null;

  function addField() {
    setFields((prev) => [
      ...prev,
      {
        key: `field_${prev.length + 1}`,
        label: "",
        type: "text",
        required: false,
        options: null,
        _clientId: `${Date.now()}-${prev.length}-${Math.random()
          .toString(36)
          .slice(2, 6)}`,
      },
    ]);
  }

  function removeField(clientId: string) {
    setFields((prev) => prev.filter((f) => f._clientId !== clientId));
  }

  function patchField(clientId: string, patch: Partial<FieldDefinition>) {
    setFields((prev) =>
      prev.map((f) => (f._clientId === clientId ? { ...f, ...patch } : f)),
    );
  }

  function onStageChange(value: string) {
    if (!value) {
      setTargetStageId(null);
      setTargetPipelineId(null);
      return;
    }
    const opt = stageOptions.find((o) => o.id === value);
    if (opt) {
      setTargetStageId(opt.id);
      setTargetPipelineId(opt.pipelineId);
    }
  }

  async function copyEmbed() {
    if (!form?.embed_snippet) return;
    try {
      await navigator.clipboard.writeText(form.embed_snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // best-effort — fall back to selection so the manager can Ctrl+C
      const el = document.getElementById(
        "embed-snippet-textarea",
      ) as HTMLTextAreaElement | null;
      el?.select();
    }
  }

  function handleSave() {
    setError(null);
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Название обязательно");
      return;
    }
    const cleanedFields = stripClientIds(fields).filter((f) =>
      f.label.trim(),
    );
    const payload = {
      name: trimmedName,
      fields_json: cleanedFields,
      target_pipeline_id: targetPipelineId,
      target_stage_id: targetStageId,
      redirect_url: redirectUrl.trim() || null,
    };

    const opts = {
      onSuccess: (saved: WebFormOut) => onSaved(saved),
      onError: (err: ApiError) => {
        const detail =
          typeof err.body === "object" && err.body
            ? (err.body as { detail?: unknown }).detail
            : null;
        setError(detail ? String(detail) : "Не удалось сохранить форму");
      },
    };

    if (isEdit && form) {
      update.mutate({ id: form.id, body: payload }, opts);
    } else {
      create.mutate(payload, opts);
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-50 backdrop-blur-[2px]"
        onClick={busy ? undefined : onClose}
        aria-hidden
      />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-label={isEdit ? "Редактирование формы" : "Новая форма"}
          className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-2xl max-h-[92vh] flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="px-6 py-4 border-b border-black/5 flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-3">
                Форма
              </div>
              <h2 className="text-lg font-bold tracking-tight text-ink mt-0.5 truncate">
                {isEdit ? form?.name : "Новая форма"}
              </h2>
              {isEdit && form?.slug && (
                <div className="text-[11px] font-mono text-muted-3 mt-0.5">
                  /{form.slug}
                </div>
              )}
            </div>
            <button
              onClick={busy ? undefined : onClose}
              disabled={busy}
              className="shrink-0 p-1.5 -mr-1.5 rounded-lg text-muted-2 hover:bg-canvas hover:text-ink transition-colors disabled:opacity-40"
              aria-label="Закрыть"
            >
              <X size={16} />
            </button>
          </div>

          {/* Tabs — only show «Встроить» when editing (need slug) */}
          <div className="px-6 pt-3 border-b border-black/5">
            <div className="flex gap-1">
              <TabButton
                active={tab === "settings"}
                onClick={() => setTab("settings")}
                icon={<Settings2 size={13} />}
                label="Настройки"
              />
              {isEdit && (
                <TabButton
                  active={tab === "embed"}
                  onClick={() => setTab("embed")}
                  icon={<Code2 size={13} />}
                  label="Встроить"
                />
              )}
            </div>
          </div>

          {/* Body */}
          <div className="px-6 py-5 overflow-y-auto flex-1">
            {tab === "settings" && (
              <SettingsTab
                name={name}
                onName={setName}
                fields={fields}
                onAddField={addField}
                onRemoveField={removeField}
                onPatchField={patchField}
                stageOptions={stageOptions}
                targetStageId={targetStageId}
                onStageChange={onStageChange}
                redirectUrl={redirectUrl}
                onRedirectUrl={setRedirectUrl}
              />
            )}
            {tab === "embed" && form && (
              <EmbedTab
                form={form}
                copied={copied}
                onCopy={copyEmbed}
              />
            )}
          </div>

          {/* Footer — only on settings tab; embed tab is read-only */}
          {tab === "settings" && (
            <div className="px-6 py-4 border-t border-black/5 flex items-center justify-between">
              {error ? (
                <div className="flex items-center gap-1.5 text-[12px] text-rose">
                  <AlertCircle size={13} />
                  <span>{error}</span>
                </div>
              ) : (
                <span />
              )}
              <div className="flex items-center gap-2">
                <button
                  onClick={busy ? undefined : onClose}
                  disabled={busy}
                  className="text-sm font-semibold text-muted hover:text-ink disabled:opacity-40 transition-colors"
                >
                  Отмена
                </button>
                <button
                  onClick={handleSave}
                  disabled={busy}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-pill bg-ink text-white text-sm font-semibold hover:bg-ink/90 disabled:opacity-40 transition-all duration-300"
                >
                  {busy && <Loader2 size={14} className="animate-spin" />}
                  {busy ? "Сохраняем…" : "Сохранить"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Tab button
// ---------------------------------------------------------------------------

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "inline-flex items-center gap-1.5 px-3 py-2 text-[12px] font-semibold border-b-2 transition-colors -mb-px",
        active
          ? "border-brand-accent text-ink"
          : "border-transparent text-muted-2 hover:text-ink",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Settings tab
// ---------------------------------------------------------------------------

function SettingsTab({
  name,
  onName,
  fields,
  onAddField,
  onRemoveField,
  onPatchField,
  stageOptions,
  targetStageId,
  onStageChange,
  redirectUrl,
  onRedirectUrl,
}: {
  name: string;
  onName: (v: string) => void;
  fields: FieldRow[];
  onAddField: () => void;
  onRemoveField: (id: string) => void;
  onPatchField: (id: string, patch: Partial<FieldDefinition>) => void;
  stageOptions: { id: string; pipelineId: string; label: string }[];
  targetStageId: string | null;
  onStageChange: (v: string) => void;
  redirectUrl: string;
  onRedirectUrl: (v: string) => void;
}) {
  return (
    <div className="space-y-5">
      {/* Name */}
      <Field label="Название" required>
        <input
          value={name}
          onChange={(e) => onName(e.target.value)}
          placeholder="Например: Заявка с лендинга QSR"
          className="w-full text-sm bg-canvas border border-black/10 rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
        />
      </Field>

      {/* Fields */}
      <div>
        <div className="flex items-baseline justify-between mb-1.5">
          <label className="text-[10px] font-mono uppercase tracking-wider text-muted-2">
            Поля формы
          </label>
          {fields.length === 0 && (
            <span className="text-[11px] text-amber-700">
              Без полей форма всё равно создаст лид (только source/UTM)
            </span>
          )}
        </div>
        <div className="rounded-2xl border border-black/5 bg-white">
          <div className="grid grid-cols-[1fr_140px_90px_24px] items-center gap-2 px-3 py-2 bg-canvas border-b border-black/5 text-[10px] font-mono uppercase tracking-wider text-muted-3">
            <span>Заголовок</span>
            <span>Тип</span>
            <span>Обязательное</span>
            <span />
          </div>
          {fields.length === 0 && (
            <div className="px-3 py-4 text-[12px] text-muted-3 text-center">
              Поля не добавлены
            </div>
          )}
          <div className="divide-y divide-black/5">
            {fields.map((f) => (
              <FieldRowEditor
                key={f._clientId}
                field={f}
                onPatch={(p) => onPatchField(f._clientId, p)}
                onRemove={() => onRemoveField(f._clientId)}
              />
            ))}
          </div>
        </div>
        <button
          onClick={onAddField}
          className="mt-2 inline-flex items-center gap-1 text-[12px] font-semibold text-muted hover:text-ink transition-colors"
        >
          <Plus size={13} />
          Добавить поле
        </button>
      </div>

      {/* Target stage */}
      <Field
        label="Целевая стадия"
        hint="Куда попадает новый лид. Если не указано — первая стадия пайплайна по умолчанию."
      >
        <select
          value={targetStageId ?? ""}
          onChange={(e) => onStageChange(e.target.value)}
          className="w-full text-sm bg-canvas border border-black/10 rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
        >
          <option value="">— по умолчанию (первая стадия)</option>
          {stageOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </Field>

      {/* Redirect URL */}
      <Field
        label="URL редиректа после отправки"
        hint="Куда отправить пользователя после успеха. Пустое — показать «Спасибо»."
      >
        <input
          value={redirectUrl}
          onChange={(e) => onRedirectUrl(e.target.value)}
          placeholder="https://drinkx.ru/thanks"
          className="w-full text-sm bg-canvas border border-black/10 rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
        />
      </Field>
    </div>
  );
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-[10px] font-mono uppercase tracking-wider text-muted-2 mb-1.5">
        {label}
        {required && <span className="text-amber-700"> *</span>}
      </label>
      {children}
      {hint && (
        <p className="text-[11px] text-muted-3 mt-1 leading-snug">{hint}</p>
      )}
    </div>
  );
}

function FieldRowEditor({
  field,
  onPatch,
  onRemove,
}: {
  field: FieldRow;
  onPatch: (patch: Partial<FieldDefinition>) => void;
  onRemove: () => void;
}) {
  return (
    <div className="grid grid-cols-[1fr_140px_90px_24px] items-center gap-2 px-3 py-2">
      <input
        value={field.label}
        onChange={(e) => onPatch({ label: e.target.value })}
        placeholder="Например: Имя"
        className="text-sm bg-canvas border border-black/10 rounded-lg px-2.5 py-1.5 outline-none focus:border-brand-accent"
      />
      <select
        value={field.type}
        onChange={(e) => onPatch({ type: e.target.value as FieldType })}
        className="text-sm bg-canvas border border-black/10 rounded-lg px-2.5 py-1.5 outline-none focus:border-brand-accent"
      >
        {FIELD_TYPES.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>
      <button
        onClick={() => onPatch({ required: !field.required })}
        className={clsx(
          "h-7 rounded-pill text-[11px] font-semibold transition-colors",
          field.required
            ? "bg-brand-accent text-white"
            : "bg-canvas text-muted-2 hover:bg-canvas-2",
        )}
        aria-pressed={field.required}
      >
        {field.required ? "Да" : "Нет"}
      </button>
      <button
        onClick={onRemove}
        className="text-muted-3 hover:text-rose-600 transition-colors"
        aria-label="Удалить поле"
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Embed tab
// ---------------------------------------------------------------------------

function EmbedTab({
  form,
  copied,
  onCopy,
}: {
  form: WebFormOut;
  copied: boolean;
  onCopy: () => void;
}) {
  // Compose the full snippet — `embed_snippet` is just the <script>
  // tag; we add the <div> mount-point so the manager has one block to
  // paste. embed.js falls back to document.currentScript.parentElement
  // when the div is missing, but providing it is cleaner.
  const fullSnippet = useMemo(() => {
    const script = form.embed_snippet ?? "";
    return `<div id="drinkx-form-${form.slug}"></div>\n${script}`;
  }, [form.embed_snippet, form.slug]);

  const directUrl = useMemo(() => {
    // Recover api_base_url from the script src in embed_snippet so
    // the direct-link card stays in sync with the snippet.
    const m = (form.embed_snippet || "").match(/src="([^"]+)"/);
    return m?.[1] ?? "";
  }, [form.embed_snippet]);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-bold tracking-tight text-ink">
          Встроить форму
        </h3>
        <p className="text-[13px] text-muted mt-1">
          Вставьте этот код в HTML страницы, где должна появиться форма.
        </p>
      </div>

      <div>
        <label className="block text-[10px] font-mono uppercase tracking-wider text-muted-2 mb-1.5">
          Код для вставки
        </label>
        <textarea
          id="embed-snippet-textarea"
          readOnly
          value={fullSnippet}
          rows={3}
          onFocus={(e) => e.currentTarget.select()}
          className="w-full text-[11px] font-mono leading-relaxed bg-canvas border border-black/10 rounded-xl p-3 outline-none focus:border-brand-accent/40 resize-none"
        />
        <div className="flex items-center justify-between mt-2">
          <span className="text-[10px] text-muted-3">
            Кликните в поле — выделится весь текст.
          </span>
          <button
            onClick={onCopy}
            className={clsx(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-[11px] font-semibold transition-all",
              copied
                ? "bg-emerald-600 text-white"
                : "bg-canvas text-ink border border-black/10 hover:bg-canvas-2",
            )}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? "Скопировано" : "Скопировать"}
          </button>
        </div>
      </div>

      {directUrl && (
        <div className="rounded-2xl border border-black/5 bg-canvas/40 px-4 py-3">
          <div className="text-[10px] font-mono uppercase tracking-wider text-muted-3 mb-1">
            Прямая ссылка на embed.js
          </div>
          <a
            href={directUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[12px] font-mono text-brand-accent hover:underline break-all"
          >
            {directUrl}
          </a>
        </div>
      )}

      <div className="rounded-2xl border border-amber-200/60 bg-amber-50 px-4 py-3 text-[12px] text-amber-900">
        <strong>Совет:</strong> при изменении полей формы slug не меняется —
        embed-код остаётся валидным, обновлять разметку на сайте не нужно.
        Если форму нужно «архивировать», переключите тумблер «Активна» в
        списке — embed-код вернёт 410 Gone, лиды перестанут приходить.
      </div>
    </div>
  );
}
