"use client";

import { useState } from "react";
import {
  CircleDollarSign,
  Package,
  Hash,
  Tag,
  TrendingUp,
  Layers,
  MapPin,
  Globe,
  Mail,
  Phone,
  Fingerprint,
  User,
  Loader2,
  Pencil,
  Sparkles,
  RefreshCw,
  ChevronDown,
} from "lucide-react";
import type { LeadOut } from "@/lib/types";
import { useUpdateDealFields } from "@/lib/hooks/use-lead-v2";
import { useUpdateLead } from "@/lib/hooks/use-lead";
import { useLatestEnrichment, useTriggerEnrichment } from "@/lib/hooks/use-enrichment";
import { ApiError } from "@/lib/api-client";
import { useMe } from "@/lib/hooks/use-me";
import { useUsers } from "@/lib/hooks/use-users";
import {
  SEGMENT_OPTIONS,
  dealTypeLabel,
  DEAL_TYPE_LABELS,
} from "@/lib/i18n";
import { C } from "@/lib/design-system";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";

interface Props {
  lead: LeadOut;
}

const PRIORITY_OPTIONS = ["A", "B", "C", "D"] as const;

function asList(v: unknown): string[] {
  if (!v) return [];
  if (Array.isArray(v))
    return v.filter((x) => typeof x === "string" && x.trim()).map((x) => String(x));
  if (typeof v === "string" && v.trim()) return [v];
  return [];
}

function asText(v: unknown): string {
  if (!v) return "";
  if (Array.isArray(v))
    return v.filter((x) => typeof x === "string" && x.trim()).join(", ");
  if (typeof v === "string") return v;
  return "";
}

function formatRub(value: number | string | null | undefined): string {
  if (value == null || value === "") return "Не указана";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "Не указана";
  return (
    new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n) +
    " ₽"
  );
}

export function LeadInfoBlock({ lead }: Props) {
  const updateLead = useUpdateLead(lead.id);
  const updateDeal = useUpdateDealFields(lead.id);
  const { data: me } = useMe();
  const usersQuery = useUsers();
  const isPending = updateLead.isPending || updateDeal.isPending;

  const ai = (lead.ai_data ?? {}) as Record<string, unknown>;
  const description = asText(ai.company_profile) || asText(ai.company_overview);
  const networkScale = asText(ai.network_scale ?? ai.scale_signals);
  const formats = asList(ai.formats);
  const formatsText = formats.length > 0 ? formats.join(" · ") : asText(ai.formats);
  const subtitle = [formatsText, networkScale].filter(Boolean).join(" · ");

  const assignedUser = usersQuery.data?.items.find(
    (u) => u.id === lead.assigned_to,
  );
  const assignedLabel = assignedUser?.email
    ? assignedUser.email
    : lead.assigned_to
      ? me?.id === lead.assigned_to
        ? "Вы"
        : lead.assigned_to.slice(0, 8)
      : "Не назначен";

  const onLeadField =
    (key: string) => async (v: string | null) => {
      await updateLead.mutateAsync({ [key]: v ?? null } as Parameters<typeof updateLead.mutateAsync>[0]);
    };

  const onDealAmount = async (v: string | null) =>
    updateDeal.mutateAsync({
      deal_amount: v == null || v === "" ? null : Number(v),
    });

  const onDealQuantity = async (v: string | null) =>
    updateDeal.mutateAsync({
      deal_quantity: v == null || v === "" ? null : Number(v),
    });

  const onDealEquipment = async (v: string | null) =>
    updateDeal.mutateAsync({ deal_equipment: v ?? null });

  const onDescription = async (v: string | null) =>
    updateLead.mutateAsync({ company_profile: v ?? "" });

  const dealTypeOptions = Object.keys(DEAL_TYPE_LABELS);
  const segmentOptions = [...SEGMENT_OPTIONS];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Информация</CardTitle>
        {isPending && (
          <Loader2 size={12} className="animate-spin text-brand-muted" />
        )}
      </CardHeader>

      {/* Editable company narrative — "что это за клиент" */}
      <DescriptionField
        value={description}
        subtitle={subtitle}
        onSave={onDescription}
      />

      {/* Notion-style property table */}
      <div className="mt-5 rounded-xl border border-brand-border overflow-hidden divide-y divide-brand-border">
        <Row
          icon={<CircleDollarSign size={15} className={C.color.muted} />}
          label="Сумма"
          value={lead.deal_amount != null ? formatRub(lead.deal_amount) : null}
          placeholder="Не указана"
          onSave={onDealAmount}
          inputType="number"
          inputProps={{ min: 0, step: "1", placeholder: "2400000" }}
        />
        <Row
          icon={<Hash size={15} className={C.color.muted} />}
          label="Количество"
          value={lead.deal_quantity?.toString() ?? null}
          placeholder="Не указано"
          onSave={onDealQuantity}
          inputType="number"
          inputProps={{ min: 0, step: "1", placeholder: "3" }}
        />
        <Row
          icon={<Package size={15} className={C.color.muted} />}
          label="Оборудование"
          value={lead.deal_equipment ?? null}
          placeholder="Не указано"
          onSave={onDealEquipment}
          inputProps={{ maxLength: 50, placeholder: "S100" }}
        />
        <Row
          icon={<Tag size={15} className={C.color.muted} />}
          label="Тип сделки"
          value={lead.deal_type ? dealTypeLabel(lead.deal_type) : null}
          placeholder="Не выбран"
          onSave={onLeadField("deal_type")}
          rawValue={lead.deal_type}
          inputType="select"
          options={dealTypeOptions}
          optionLabel={(v) => DEAL_TYPE_LABELS[v] ?? v}
        />
        <Row
          icon={<TrendingUp size={15} className={C.color.muted} />}
          label="Приоритет"
          value={lead.priority ?? null}
          placeholder="Не задан"
          onSave={onLeadField("priority")}
          inputType="select"
          options={[...PRIORITY_OPTIONS]}
        />
        <Row
          icon={<Layers size={15} className={C.color.muted} />}
          label="Сегмент"
          value={lead.segment ?? null}
          placeholder="Не задан"
          rawValue={lead.segment}
          onSave={onLeadField("segment")}
          inputType="select"
          options={segmentOptions}
        />
        <Row
          icon={<MapPin size={15} className={C.color.muted} />}
          label="Город"
          value={lead.city ?? null}
          placeholder="Не указан"
          onSave={onLeadField("city")}
          inputProps={{ maxLength: 120, placeholder: "Москва" }}
        />
        <Row
          icon={<Fingerprint size={15} className={C.color.muted} />}
          label="ИНН"
          value={lead.inn ?? null}
          placeholder="Не указан"
          onSave={onLeadField("inn")}
          inputProps={{ maxLength: 20, placeholder: "7707083893" }}
        />
        <Row
          icon={<Globe size={15} className={C.color.muted} />}
          label="Сайт"
          value={lead.website ?? null}
          placeholder="Не указан"
          onSave={onLeadField("website")}
          inputProps={{ maxLength: 512, placeholder: "example.ru" }}
        />
        <Row
          icon={<Mail size={15} className={C.color.muted} />}
          label="Email"
          value={lead.email ?? null}
          placeholder="Не указан"
          onSave={onLeadField("email")}
          inputType="email"
          inputProps={{ maxLength: 254, placeholder: "info@example.ru" }}
        />
        <Row
          icon={<Phone size={15} className={C.color.muted} />}
          label="Телефон"
          value={lead.phone ?? null}
          placeholder="Не указан"
          onSave={onLeadField("phone")}
          inputType="tel"
          inputProps={{ maxLength: 30, placeholder: "+7 999 111-22-33" }}
        />
        <Row
          icon={<User size={15} className={C.color.muted} />}
          label="Ответственный"
          value={assignedLabel}
          readOnly
          hint={lead.assigned_to ? "Изменяется через «Передать»" : undefined}
        />
      </div>

      {/* Collapsible, read-only AI Бриф (updated only via enrichment) */}
      <AIBriefSection lead={lead} ai={ai} />
    </Card>
  );
}

function DescriptionField({
  value,
  subtitle,
  onSave,
}: {
  value: string;
  subtitle: string;
  onSave: (v: string | null) => Promise<unknown>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  function startEdit() {
    setDraft(value);
    setEditing(true);
  }

  async function commit() {
    setBusy(true);
    try {
      await onSave(draft.trim() === "" ? null : draft.trim());
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <textarea
        autoFocus
        rows={3}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Escape") setEditing(false);
        }}
        disabled={busy}
        placeholder="Кто этот клиент, чем занимается, масштаб…"
        className="w-full type-caption leading-relaxed bg-brand-bg border border-brand-accent/40 rounded-xl px-3 py-2 focus:outline-none focus:border-brand-accent resize-y"
      />
    );
  }

  return (
    <div
      onClick={startEdit}
      className="group cursor-text rounded-xl -mx-2 px-2 py-1.5 hover:bg-brand-bg transition-colors"
    >
      <div className="flex items-start gap-2">
        <p className={`flex-1 type-caption leading-relaxed ${value ? C.color.text : C.color.muted}`}>
          {value || "Описание не задано — нажмите, чтобы добавить"}
        </p>
        <Pencil
          size={12}
          className="text-brand-muted opacity-0 group-hover:opacity-100 transition-opacity mt-1 shrink-0"
        />
      </div>
      {subtitle && (
        <p className={`type-caption ${C.color.muted} mt-1`}>{subtitle}</p>
      )}
    </div>
  );
}

interface RowProps {
  icon: React.ReactNode;
  label: string;
  value: string | null;
  placeholder?: string;
  hint?: string;
  readOnly?: boolean;
  rawValue?: string | null;
  onSave?: (v: string | null) => Promise<unknown>;
  inputType?: "text" | "number" | "email" | "tel" | "select";
  inputProps?: React.InputHTMLAttributes<HTMLInputElement>;
  options?: string[];
  optionLabel?: (v: string) => string;
}

function Row({
  icon,
  label,
  value,
  placeholder = "—",
  hint,
  readOnly,
  rawValue,
  onSave,
  inputType = "text",
  inputProps,
  options,
  optionLabel,
}: RowProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const editable = !readOnly && !!onSave;

  function startEdit() {
    if (!editable) return;
    setDraft(rawValue ?? value ?? "");
    setEditing(true);
  }

  async function commit() {
    if (!onSave) return;
    setBusy(true);
    try {
      await onSave(draft.trim() === "" ? null : draft.trim());
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      onClick={editing ? undefined : startEdit}
      className={`grid grid-cols-[7.5rem_1fr] sm:grid-cols-[10rem_1fr] group ${
        editable && !editing
          ? "cursor-text hover:bg-brand-bg transition-colors"
          : ""
      }`}
    >
      {/* Property name cell */}
      <div className="flex items-center gap-2 px-3 py-2.5 bg-brand-panel/40 border-r border-brand-border">
        <span className="shrink-0">{icon}</span>
        <span className={`type-caption ${C.color.muted} truncate`}>{label}</span>
      </div>

      {/* Value cell */}
      <div className="px-3 py-2 flex items-center gap-2 min-w-0">
        {editing ? (
          inputType === "select" ? (
            <select
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => {
                if (e.key === "Escape") setEditing(false);
                if (e.key === "Enter") void commit();
              }}
              disabled={busy}
              className="w-full type-body bg-brand-bg border border-brand-accent/40 rounded-lg px-2 py-1 focus:outline-none focus:border-brand-accent"
            >
              <option value="">— очистить —</option>
              {(options ?? []).map((opt) => (
                <option key={opt} value={opt}>
                  {optionLabel ? optionLabel(opt) : opt}
                </option>
              ))}
            </select>
          ) : (
            <input
              autoFocus
              type={inputType}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => {
                if (e.key === "Escape") setEditing(false);
                if (e.key === "Enter") void commit();
              }}
              disabled={busy}
              {...inputProps}
              className="w-full type-body bg-brand-bg border border-brand-accent/40 rounded-lg px-2 py-1 focus:outline-none focus:border-brand-accent"
            />
          )
        ) : (
          <>
            <div className="min-w-0 flex-1">
              <span className={`type-body ${value ? C.color.text : C.color.muted}`}>
                {value ?? placeholder}
              </span>
              {hint && (
                <span className={`block type-caption ${C.color.muted} mt-0.5`}>
                  {hint}
                </span>
              )}
            </div>
            {editable && (
              <Pencil
                size={12}
                className="text-brand-muted opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function AIBriefSection({
  lead,
  ai,
}: {
  lead: LeadOut;
  ai: Record<string, unknown>;
}) {
  const hasAiData =
    Object.keys(ai).length > 0 &&
    Boolean(ai.company_profile || ai.company_overview);
  const { data: run } = useLatestEnrichment(lead.id);
  const trigger = useTriggerEnrichment(lead.id);
  const [open, setOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  }

  function handleRun(mode: "full" | "append" | "lightweight") {
    trigger.mutate(mode, {
      onSuccess: () => showToast("AI Бриф в очереди — обычно 5–10 сек"),
      onError: (err) => {
        if (err instanceof ApiError && err.status === 409) {
          showToast("Enrichment уже запущен");
        } else {
          showToast("Не удалось запустить enrichment");
        }
      },
    });
  }

  const isRunning = run?.status === "running" || trigger.isPending;
  const coffee = asList(ai.coffee_signals);
  const growth = asList(ai.growth_signals);
  const triggers = asList(ai.sales_triggers);
  const entryRoute = asText(ai.entry_route) || asList(ai.next_steps).join(" · ");
  const sources = asList(ai.sources_used);
  const sourceLabel = run?.provider || (hasAiData ? "База знаний" : "AI не запускали");

  return (
    <section className="mt-5 pt-4 border-t border-brand-border">
      <header className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 min-w-0 group"
          aria-expanded={open}
        >
          <ChevronDown
            size={15}
            className={`text-brand-muted transition-transform ${open ? "" : "-rotate-90"}`}
          />
          <Sparkles size={16} className="text-warning shrink-0" />
          <h3 className={`type-card-title font-bold ${C.color.text}`}>AI Бриф</h3>
          <span className={`type-caption ${C.color.muted} font-mono truncate`}>
            · {sourceLabel}
          </span>
        </button>
        {hasAiData && (
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => handleRun("lightweight")}
              disabled={isRunning}
              title="Бесплатное обновление: новости отрасли + сайт + вакансии, без Brave"
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 type-body font-semibold ${C.button.ghost} disabled:opacity-50 transition-opacity`}
            >
              Обновить
            </button>
            <button
              type="button"
              onClick={() => handleRun("append")}
              disabled={isRunning}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 type-body font-semibold ${C.button.ghost} disabled:opacity-50 transition-opacity`}
            >
              {isRunning ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <RefreshCw size={13} />
              )}
              Дополнить
            </button>
          </div>
        )}
      </header>

      {open && (
        <div className="mt-4">
          {!hasAiData ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Sparkles size={28} className="text-warning mb-3" />
              <p className={`type-caption font-semibold ${C.color.text} mb-1`}>
                Бриф пока пуст
              </p>
              <p className={`type-caption ${C.color.muted} mb-5 max-w-sm`}>
                Запустите enrichment — AI соберёт данные из Brave, HH.ru и сайта
                компании, заполнит обзор, сигналы и следующий шаг.
              </p>
              <button
                type="button"
                onClick={() => handleRun("full")}
                disabled={isRunning}
                className="inline-flex items-center gap-2 px-5 py-2 type-body font-semibold bg-brand-accent text-white rounded-full disabled:opacity-50 transition-opacity"
              >
                {isRunning ? (
                  <>
                    <Loader2 size={14} className="animate-spin" /> Идёт enrichment…
                  </>
                ) : (
                  <>
                    <Sparkles size={14} /> Запустить enrichment
                  </>
                )}
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {coffee.length > 0 && (
                <Block title="Кофе / foodservice сигналы" items={coffee} />
              )}
              {growth.length > 0 && <Block title="Growth signals" items={growth} />}
              {triggers.length > 0 && (
                <Block title="Sales triggers" items={triggers} />
              )}
              {entryRoute && <Block title="Маршрут входа" items={[entryRoute]} />}

              {sources.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-3 border-t border-brand-border">
                  {sources.map((s, i) => (
                    <span
                      key={`${s}-${i}`}
                      className={`type-caption font-mono ${C.color.muted} bg-brand-panel px-2.5 py-1 rounded-full`}
                    >
                      {s.length > 40 ? `${s.slice(0, 40)}…` : s}
                    </span>
                  ))}
                </div>
              )}

              <p className="type-hint text-brand-muted pt-1">
                Сигналы заполняет AI — правьте их через «Обновить» / «Дополнить».
                Текстовое описание выше можно редактировать вручную.
              </p>
            </div>
          )}
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-brand-accent text-white type-caption font-semibold px-5 py-2 rounded-full z-50">
          {toast}
        </div>
      )}
    </section>
  );
}

function Block({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="type-caption text-brand-muted mb-2">{title}</p>
      <ul className={`type-caption ${C.color.text} space-y-1.5 leading-relaxed`}>
        {items.map((it, i) => (
          <li key={i} className="flex gap-2">
            <span className={`${C.color.muted} shrink-0`}>·</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
