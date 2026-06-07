"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  Code2,
  Copy,
  Loader2,
  Plus,
  RefreshCw,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import { clsx } from "clsx";

import { useCreateForm, useRotateFormKey, useUpdateForm } from "@/lib/hooks/use-forms";
import { usePipelines } from "@/lib/hooks/use-pipelines";
import { useUsers } from "@/lib/hooks/use-users";
import { ApiError } from "@/lib/api-client";
import type {
  FieldDefinition,
  FieldType,
  WebFormOut,
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  const [defaultAssigneeId, setDefaultAssigneeId] = useState<string | null>(null);
  const [contactTaskSlaHours, setContactTaskSlaHours] = useState(2);
  const [sourceLabel, setSourceLabel] = useState("");
  const [notifyEmail, setNotifyEmail] = useState("");
  const [requireKey, setRequireKey] = useState(false);
  const [autoreplyEnabled, setAutoreplyEnabled] = useState(false);
  const [autoreplySubject, setAutoreplySubject] = useState("");
  const [autoreplyBody, setAutoreplyBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const create = useCreateForm();
  const update = useUpdateForm();
  const rotateKey = useRotateFormKey();
  const pipelinesQuery = usePipelines();
  const usersQuery = useUsers();

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
      setDefaultAssigneeId(form.default_assignee_id ?? null);
      setContactTaskSlaHours(form.contact_task_sla_hours ?? 2);
      setSourceLabel(form.source_label ?? "");
      setNotifyEmail(form.notify_email ?? "");
      setRequireKey(!!form.ingest_token);
      setAutoreplyEnabled(form.autoreply_enabled ?? false);
      setAutoreplySubject(form.autoreply_subject ?? "");
      setAutoreplyBody(form.autoreply_body ?? "");
    } else {
      setName("");
      setFields(withClientIds(DEFAULT_FIELDS));
      setTargetStageId(null);
      setTargetPipelineId(null);
      setRedirectUrl("");
      setDefaultAssigneeId(null);
      setContactTaskSlaHours(2);
      setSourceLabel("");
      setNotifyEmail("");
      setRequireKey(false);
      setAutoreplyEnabled(false);
      setAutoreplySubject("");
      setAutoreplyBody("");
    }
  }, [open, form]);

  // Esc closes the modal — but not while a save is in flight, otherwise
  // the manager could close mid-mutation and miss the success/failure.
  const busy = create.isPending || update.isPending || rotateKey.isPending;
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
      default_assignee_id: defaultAssigneeId || null,
      contact_task_sla_hours: contactTaskSlaHours,
      source_label: sourceLabel.trim() || null,
      notify_email: notifyEmail.trim() || null,
      require_key: requireKey,
      autoreply_enabled: autoreplyEnabled,
      autoreply_subject: autoreplySubject.trim() || null,
      autoreply_body: autoreplyBody.trim() || null,
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
          className="bg-white rounded-card border border-brand-border shadow-overlay w-full max-w-2xl max-h-[92vh] flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="px-6 py-4 border-b border-brand-border flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-2xs font-mono uppercase tracking-wider text-brand-muted">
                Форма
              </div>
              <h2 className="text-lg font-bold tracking-tight text-brand-primary mt-0.5 truncate">
                {isEdit ? form?.name : "Новая форма"}
              </h2>
              {isEdit && form?.slug && (
                <div className="text-xs font-mono text-brand-muted mt-0.5">
                  /{form.slug}
                </div>
              )}
            </div>
            <button
              onClick={busy ? undefined : onClose}
              disabled={busy}
              className="shrink-0 p-1.5 -mr-1.5 rounded-lg text-brand-muted hover:bg-brand-bg hover:text-brand-primary transition-colors disabled:opacity-40"
              aria-label="Закрыть"
            >
              <X size={16} />
            </button>
          </div>

          {/* Tabs — only show «Встроить» when editing (need slug) */}
          <div className="px-6 pt-3 border-b border-brand-border">
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
                users={usersQuery.data?.items ?? []}
                defaultAssigneeId={defaultAssigneeId}
                onDefaultAssigneeId={setDefaultAssigneeId}
                contactTaskSlaHours={contactTaskSlaHours}
                onContactTaskSlaHours={setContactTaskSlaHours}
                sourceLabel={sourceLabel}
                onSourceLabel={setSourceLabel}
                notifyEmail={notifyEmail}
                onNotifyEmail={setNotifyEmail}
                requireKey={requireKey}
                onRequireKey={setRequireKey}
                autoreplyEnabled={autoreplyEnabled}
                onAutoreplyEnabled={setAutoreplyEnabled}
                autoreplySubject={autoreplySubject}
                onAutoreplySubject={setAutoreplySubject}
                autoreplyBody={autoreplyBody}
                onAutoreplyBody={setAutoreplyBody}
              />
            )}
            {tab === "embed" && form && (
              <EmbedTab
                form={form}
                copied={copied}
                onCopy={copyEmbed}
                onRotateKey={() => rotateKey.mutate(form.id)}
                rotatingKey={rotateKey.isPending}
              />
            )}
          </div>

          {/* Footer — only on settings tab; embed tab is read-only */}
          {tab === "settings" && (
            <div className="px-6 py-4 border-t border-brand-border flex items-center justify-between">
              {error ? (
                <div className="flex items-center gap-1.5 text-sm text-rose">
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
                  className="text-sm font-semibold text-brand-muted hover:text-brand-primary disabled:opacity-40 transition-colors"
                >
                  Отмена
                </button>
                <button
                  onClick={handleSave}
                  disabled={busy}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-brand-accent text-white text-sm font-semibold hover:bg-brand-accent/90 disabled:opacity-40 transition-all duration-300"
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
        "inline-flex items-center gap-1.5 px-3 py-2 text-sm font-semibold border-b-2 transition-colors -mb-px",
        active
          ? "border-brand-accent text-brand-primary"
          : "border-transparent text-brand-muted hover:text-brand-primary",
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
  users,
  defaultAssigneeId,
  onDefaultAssigneeId,
  contactTaskSlaHours,
  onContactTaskSlaHours,
  sourceLabel,
  onSourceLabel,
  notifyEmail,
  onNotifyEmail,
  requireKey,
  onRequireKey,
  autoreplyEnabled,
  onAutoreplyEnabled,
  autoreplySubject,
  onAutoreplySubject,
  autoreplyBody,
  onAutoreplyBody,
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
  users: { id: string; name: string; email: string }[];
  defaultAssigneeId: string | null;
  onDefaultAssigneeId: (v: string | null) => void;
  contactTaskSlaHours: number;
  onContactTaskSlaHours: (v: number) => void;
  sourceLabel: string;
  onSourceLabel: (v: string) => void;
  notifyEmail: string;
  onNotifyEmail: (v: string) => void;
  requireKey: boolean;
  onRequireKey: (v: boolean) => void;
  autoreplyEnabled: boolean;
  onAutoreplyEnabled: (v: boolean) => void;
  autoreplySubject: string;
  onAutoreplySubject: (v: string) => void;
  autoreplyBody: string;
  onAutoreplyBody: (v: string) => void;
}) {
  return (
    <div className="space-y-5">
      {/* Name */}
      <Field label="Название" required>
        <input
          value={name}
          onChange={(e) => onName(e.target.value)}
          placeholder="Например: Заявка с лендинга QSR"
          className="w-full text-sm bg-brand-bg border border-brand-border rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
        />
      </Field>

      {/* Fields */}
      <div>
        <div className="flex items-baseline justify-between mb-1.5">
          <label className="text-2xs font-mono uppercase tracking-wider text-brand-muted">
            Поля формы
          </label>
          {fields.length === 0 && (
            <span className="text-xs text-amber-700">
              Без полей форма всё равно создаст лид (только source/UTM)
            </span>
          )}
        </div>
        <div className="rounded-card border border-brand-border bg-white">
          <div className="grid grid-cols-[1fr_140px_90px_24px] items-center gap-2 px-3 py-2 bg-brand-bg border-b border-brand-border text-2xs font-mono uppercase tracking-wider text-brand-muted">
            <span>Заголовок</span>
            <span>Тип</span>
            <span>Обязательное</span>
            <span />
          </div>
          {fields.length === 0 && (
            <div className="px-3 py-4 text-sm text-brand-muted text-center">
              Поля не добавлены
            </div>
          )}
          <div className="divide-y divide-brand-border">
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
          className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-brand-muted hover:text-brand-primary transition-colors"
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
          className="w-full text-sm bg-brand-bg border border-brand-border rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
        >
          <option value="">— по умолчанию (первая стадия)</option>
          {stageOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </Field>

      {/* Default assignee */}
      <Field
        label="Ответственный менеджер"
        hint="Кому назначаются лиды из этой формы. Пустое — в общий пул."
      >
        <select
          value={defaultAssigneeId ?? ""}
          onChange={(e) => onDefaultAssigneeId(e.target.value || null)}
          className="w-full text-sm bg-brand-bg border border-brand-border rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
        >
          <option value="">— в общий пул —</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name || u.email}
            </option>
          ))}
        </select>
      </Field>

      {/* SLA */}
      <Field
        label="SLA, часов"
        hint="Через сколько часов задача по контакту становится просроченной (1–240)."
      >
        <input
          type="number"
          min={1}
          max={240}
          value={contactTaskSlaHours}
          onChange={(e) => onContactTaskSlaHours(Math.min(240, Math.max(1, Number(e.target.value))))}
          className="w-full text-sm bg-brand-bg border border-brand-border rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
        />
      </Field>

      {/* Source label */}
      <Field
        label="Название канала (для аналитики)"
        hint="Метка источника лида, видная в аналитике. Например: «landing-qsr»."
      >
        <input
          value={sourceLabel}
          onChange={(e) => onSourceLabel(e.target.value)}
          placeholder="Например: landing-horeca"
          className="w-full text-sm bg-brand-bg border border-brand-border rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
        />
      </Field>

      {/* Notify email */}
      <Field
        label="Email для уведомлений"
        hint="На этот адрес придёт письмо при каждой новой заявке."
      >
        <input
          type="email"
          value={notifyEmail}
          onChange={(e) => onNotifyEmail(e.target.value)}
          placeholder="manager@drinkx.ru"
          className="w-full text-sm bg-brand-bg border border-brand-border rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
        />
      </Field>

      {/* Require key */}
      <div>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={requireKey}
            onChange={(e) => onRequireKey(e.target.checked)}
            className="h-4 w-4 rounded border-brand-border accent-brand-accent"
          />
          <span className="text-sm font-semibold text-brand-primary">
            Защищённый приём (S2S ключ)
          </span>
        </label>
        <p className="text-xs text-brand-muted mt-1 leading-snug ml-7">
          При включении все запросы к эндпоинту должны содержать заголовок{" "}
          <code className="font-mono">X-Form-Key</code>. Ключ генерируется
          автоматически и виден во вкладке «Встроить».
        </p>
      </div>

      {/* Auto-reply to the lead */}
      <div>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={autoreplyEnabled}
            onChange={(e) => onAutoreplyEnabled(e.target.checked)}
            className="h-4 w-4 rounded border-brand-border accent-brand-accent"
          />
          <span className="text-sm font-semibold text-brand-primary">
            Авто-ответ на почту лида
          </span>
        </label>
        <p className="text-xs text-brand-muted mt-1 leading-snug ml-7">
          Если в заявке указана почта — на неё автоматически уйдёт это
          письмо (например, КП и ссылка на калькулятор). Без почты —
          просто не отправится.
        </p>
      </div>

      {autoreplyEnabled && (
        <>
          <Field label="Тема письма">
            <input
              value={autoreplySubject}
              onChange={(e) => onAutoreplySubject(e.target.value)}
              placeholder="DrinkX — коммерческое предложение"
              className="w-full text-sm bg-brand-bg border border-brand-border rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
            />
          </Field>
          <Field
            label="Текст письма"
            hint="Обычный текст. Вставьте ссылку на КП и на калькулятор — в письме они станут кликабельными."
          >
            <textarea
              value={autoreplyBody}
              onChange={(e) => onAutoreplyBody(e.target.value)}
              rows={6}
              placeholder={
                "Здравствуйте!\n\nСпасибо за заявку. Наше коммерческое предложение: https://...\nКалькулятор окупаемости: https://..."
              }
              className="w-full text-sm bg-brand-bg border border-brand-border rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors resize-none"
            />
          </Field>
        </>
      )}

      {/* Redirect URL */}
      <Field
        label="URL редиректа после отправки"
        hint="Куда отправить пользователя после успеха. Пустое — показать «Спасибо»."
      >
        <input
          value={redirectUrl}
          onChange={(e) => onRedirectUrl(e.target.value)}
          placeholder="https://drinkx.ru/thanks"
          className="w-full text-sm bg-brand-bg border border-brand-border rounded-lg px-3 py-2 outline-none focus:border-brand-accent transition-colors"
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
      <label className="block text-2xs font-mono uppercase tracking-wider text-brand-muted mb-1.5">
        {label}
        {required && <span className="text-amber-700"> *</span>}
      </label>
      {children}
      {hint && (
        <p className="text-xs text-brand-muted mt-1 leading-snug">{hint}</p>
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
        className="text-sm bg-brand-bg border border-brand-border rounded-lg px-2.5 py-1.5 outline-none focus:border-brand-accent"
      />
      <select
        value={field.type}
        onChange={(e) => onPatch({ type: e.target.value as FieldType })}
        className="text-sm bg-brand-bg border border-brand-border rounded-lg px-2.5 py-1.5 outline-none focus:border-brand-accent"
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
          "h-7 rounded-full text-xs font-semibold transition-colors",
          field.required
            ? "bg-brand-accent text-white"
            : "bg-brand-bg text-brand-muted hover:bg-brand-panel",
        )}
        aria-pressed={field.required}
      >
        {field.required ? "Да" : "Нет"}
      </button>
      <button
        onClick={onRemove}
        className="text-brand-muted hover:text-rose transition-colors"
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
  onRotateKey,
  rotatingKey,
}: {
  form: WebFormOut;
  copied: boolean;
  onCopy: () => void;
  onRotateKey: () => void;
  rotatingKey: boolean;
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

  const curlExample = useMemo(() => {
    if (!form.ingest_token) return null;
    return `curl -X POST ${API_BASE}/api/public/forms/${form.slug}/submit \\
  -H "Content-Type: application/json" \\
  -H "X-Form-Key: ${form.ingest_token}" \\
  -d '{"company":"ООО Ромашка","phone":"+7...","comment":"..."}'`;
  }, [form.ingest_token, form.slug]);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-bold tracking-tight text-brand-primary">
          Встроить форму
        </h3>
        <p className="text-md text-brand-muted mt-1">
          Вставьте этот код в HTML страницы, где должна появиться форма.
        </p>
      </div>

      <div>
        <label className="block text-2xs font-mono uppercase tracking-wider text-brand-muted mb-1.5">
          Код для вставки
        </label>
        <textarea
          id="embed-snippet-textarea"
          readOnly
          value={fullSnippet}
          rows={3}
          onFocus={(e) => e.currentTarget.select()}
          className="w-full text-xs font-mono leading-relaxed bg-brand-bg border border-brand-border rounded-xl p-3 outline-none focus:border-brand-accent/40 resize-none"
        />
        <div className="flex items-center justify-between mt-2">
          <span className="text-2xs text-brand-muted">
            Кликните в поле — выделится весь текст.
          </span>
          <button
            onClick={onCopy}
            className={clsx(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all",
              copied
                ? "bg-emerald-600 text-white"
                : "bg-brand-bg text-brand-primary border border-brand-border hover:bg-brand-panel",
            )}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? "Скопировано" : "Скопировать"}
          </button>
        </div>
      </div>

      {directUrl && (
        <div className="rounded-card border border-brand-border bg-brand-bg/40 px-4 py-3">
          <div className="text-2xs font-mono uppercase tracking-wider text-brand-muted mb-1">
            Прямая ссылка на embed.js
          </div>
          <a
            href={directUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-mono text-brand-accent hover:underline break-all"
          >
            {directUrl}
          </a>
        </div>
      )}

      {curlExample && (
        <div className="space-y-3">
          <div>
            <h3 className="text-base font-bold tracking-tight text-brand-primary">
              Интеграция (S2S)
            </h3>
            <p className="text-md text-brand-muted mt-1">
              Сервер-серверная отправка. Передавайте ключ в заголовке{" "}
              <code className="font-mono text-xs">X-Form-Key</code>.
            </p>
          </div>
          <div>
            <label className="block text-2xs font-mono uppercase tracking-wider text-brand-muted mb-1.5">
              Пример запроса (curl)
            </label>
            <pre className="w-full text-xs font-mono leading-relaxed bg-brand-bg border border-brand-border rounded-xl p-3 whitespace-pre-wrap break-all">
              {curlExample}
            </pre>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-brand-muted">
              Ключ:{" "}
              <code className="font-mono">{form.ingest_token}</code>
            </span>
            <button
              onClick={onRotateKey}
              disabled={rotatingKey}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-brand-bg text-brand-primary border border-brand-border hover:bg-brand-panel disabled:opacity-40 transition-all"
            >
              {rotatingKey ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <RefreshCw size={12} />
              )}
              Перевыпустить ключ
            </button>
          </div>
        </div>
      )}

      <div className="rounded-card border border-amber-200/60 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <strong>Совет:</strong> при изменении полей формы slug не меняется —
        embed-код остаётся валидным, обновлять разметку на сайте не нужно.
        Если форму нужно «архивировать», переключите тумблер «Активна» в
        списке — embed-код вернёт 410 Gone, лиды перестанут приходить.
      </div>
    </div>
  );
}
