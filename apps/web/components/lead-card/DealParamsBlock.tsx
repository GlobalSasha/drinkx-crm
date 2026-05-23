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
} from "lucide-react";
import type { LeadOut } from "@/lib/types";
import { useUpdateDealFields } from "@/lib/hooks/use-lead-v2";
import { useUpdateLead } from "@/lib/hooks/use-lead";
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

function formatRub(value: number | string | null | undefined): string {
  if (value == null || value === "") return "Не указана";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "Не указана";
  return (
    new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n) +
    " ₽"
  );
}

export function DealParamsBlock({ lead }: Props) {
  const updateLead = useUpdateLead(lead.id);
  const updateDeal = useUpdateDealFields(lead.id);
  const { data: me } = useMe();
  const usersQuery = useUsers();
  const isPending = updateLead.isPending || updateDeal.isPending;

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

  const dealTypeOptions = Object.keys(DEAL_TYPE_LABELS);
  const segmentOptions = [...SEGMENT_OPTIONS];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Параметры сделки</CardTitle>
        {isPending && (
          <Loader2 size={12} className="animate-spin text-brand-muted" />
        )}
      </CardHeader>
      <ul className="space-y-3">
        <Row
          icon={<CircleDollarSign size={16} className={C.color.muted} />}
          label="Сумма"
          value={
            lead.deal_amount != null
              ? formatRub(lead.deal_amount)
              : null
          }
          placeholder="Не указана"
          onSave={onDealAmount}
          inputType="number"
          inputProps={{ min: 0, step: "1", placeholder: "2400000" }}
        />
        <Row
          icon={<Hash size={16} className={C.color.muted} />}
          label="Количество"
          value={lead.deal_quantity?.toString() ?? null}
          placeholder="Не указано"
          onSave={onDealQuantity}
          inputType="number"
          inputProps={{ min: 0, step: "1", placeholder: "3" }}
        />
        <Row
          icon={<Package size={16} className={C.color.muted} />}
          label="Оборудование"
          value={lead.deal_equipment ?? null}
          placeholder="Не указано"
          onSave={onDealEquipment}
          inputProps={{ maxLength: 50, placeholder: "S100" }}
        />
        <Row
          icon={<Tag size={16} className={C.color.muted} />}
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
          icon={<TrendingUp size={16} className={C.color.muted} />}
          label="Приоритет"
          value={lead.priority ?? null}
          placeholder="Не задан"
          onSave={onLeadField("priority")}
          inputType="select"
          options={[...PRIORITY_OPTIONS]}
        />
        <Row
          icon={<Layers size={16} className={C.color.muted} />}
          label="Сегмент"
          value={lead.segment ?? null}
          placeholder="Не задан"
          rawValue={lead.segment}
          onSave={onLeadField("segment")}
          inputType="select"
          options={segmentOptions}
        />
        <Row
          icon={<MapPin size={16} className={C.color.muted} />}
          label="Город"
          value={lead.city ?? null}
          placeholder="Не указан"
          onSave={onLeadField("city")}
          inputProps={{ maxLength: 120, placeholder: "Москва" }}
        />
        <Row
          icon={<Fingerprint size={16} className={C.color.muted} />}
          label="ИНН"
          value={lead.inn ?? null}
          placeholder="Не указан"
          onSave={onLeadField("inn")}
          inputProps={{ maxLength: 20, placeholder: "7707083893" }}
        />
        <Row
          icon={<Globe size={16} className={C.color.muted} />}
          label="Сайт"
          value={lead.website ?? null}
          placeholder="Не указан"
          onSave={onLeadField("website")}
          inputProps={{ maxLength: 512, placeholder: "example.ru" }}
        />
        <Row
          icon={<Mail size={16} className={C.color.muted} />}
          label="Email"
          value={lead.email ?? null}
          placeholder="Не указан"
          onSave={onLeadField("email")}
          inputType="email"
          inputProps={{ maxLength: 254, placeholder: "info@example.ru" }}
        />
        <Row
          icon={<Phone size={16} className={C.color.muted} />}
          label="Телефон"
          value={lead.phone ?? null}
          placeholder="Не указан"
          onSave={onLeadField("phone")}
          inputType="tel"
          inputProps={{ maxLength: 30, placeholder: "+7 999 111-22-33" }}
        />
        <Row
          icon={<User size={16} className={C.color.muted} />}
          label="Ответственный"
          value={assignedLabel}
          readOnly
          hint={
            lead.assigned_to ? "Изменяется через «Передать»" : undefined
          }
        />
      </ul>
    </Card>
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

  function startEdit() {
    if (readOnly || !onSave) return;
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

  if (editing) {
    return (
      <li className="flex items-start gap-3">
        <span className="mt-2 shrink-0">{icon}</span>
        <div className="min-w-0 flex-1">
          <label className="type-caption text-brand-muted block mb-1">
            {label}
          </label>
          {inputType === "select" ? (
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
              className="w-full type-body bg-canvas border border-brand-accent/40 rounded-lg px-2 py-1.5 focus:outline-none focus:border-brand-accent"
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
              className="w-full type-body bg-canvas border border-brand-accent/40 rounded-lg px-2 py-1.5 focus:outline-none focus:border-brand-accent"
            />
          )}
        </div>
      </li>
    );
  }

  return (
    <li
      onClick={startEdit}
      className={`flex items-start gap-3 group ${
        readOnly || !onSave
          ? ""
          : "cursor-text hover:bg-brand-bg rounded-xl -mx-2 px-2 py-1 transition-colors"
      }`}
    >
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className={`type-caption ${C.color.muted} mb-0.5`}>{label}</div>
        <div className={`type-body ${value ? C.color.text : C.color.muted}`}>
          {value ?? placeholder}
        </div>
        {hint && (
          <div className={`type-caption ${C.color.muted} mt-0.5`}>{hint}</div>
        )}
      </div>
      {!readOnly && onSave && (
        <Pencil
          size={12}
          className="text-brand-muted opacity-0 group-hover:opacity-100 transition-opacity mt-1 shrink-0"
        />
      )}
    </li>
  );
}
