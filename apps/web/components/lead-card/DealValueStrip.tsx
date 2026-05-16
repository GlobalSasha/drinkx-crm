"use client";

import { useState } from "react";
import { Loader2, Package, Pencil, Plus, Wallet } from "lucide-react";
import type { LeadOut } from "@/lib/types";
import { useUpdateDealFields } from "@/lib/hooks/use-lead-v2";
import { Modal } from "@/components/ui/Modal";

interface Props {
  lead: LeadOut;
}

function formatRub(value: number | string | null | undefined): string | null {
  if (value == null || value === "") return null;
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return null;
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 0,
  }).format(n) + " ₽";
}

/**
 * Compact strip above the tabs: deal sum + equipment (count × model)
 * + edit pencil. Empty state (all three fields null) shows a single
 * «＋ Добавить детали сделки» placeholder.
 */
export function DealValueStrip({ lead }: Props) {
  const [editing, setEditing] = useState(false);

  const amountText = formatRub(lead.deal_amount);
  const equipmentText =
    lead.deal_quantity && lead.deal_equipment
      ? `${lead.deal_quantity} × ${lead.deal_equipment}`
      : lead.deal_equipment ?? null;

  const isEmpty = !amountText && !equipmentText;

  return (
    <div className="rounded-2xl border border-brand-border bg-white px-4 py-2.5">
      {isEmpty ? (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="flex items-center gap-2 type-caption text-brand-muted hover:text-brand-accent-text transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 rounded-full px-1"
        >
          <Plus size={13} />
          Добавить детали сделки
        </button>
      ) : (
        <div className="flex items-center gap-4 flex-wrap">
          {amountText && (
            <span className="inline-flex items-center gap-1.5 type-body">
              <Wallet size={13} className="text-brand-muted" />
              <span className="text-brand-muted">Сумма сделки:</span>
              <span className="font-semibold text-brand-primary tabular-nums">
                {amountText}
              </span>
            </span>
          )}
          {equipmentText && (
            <span className="inline-flex items-center gap-1.5 type-body">
              <Package size={13} className="text-brand-muted" />
              <span className="text-brand-muted">Оборудование:</span>
              <span className="font-semibold text-brand-primary">
                {equipmentText}
              </span>
            </span>
          )}
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 type-caption text-brand-muted hover:text-brand-accent-text transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 rounded-full"
            aria-label="Редактировать детали сделки"
          >
            <Pencil size={11} />
            Редактировать
          </button>
        </div>
      )}

      {editing && (
        <DealEditModal lead={lead} onClose={() => setEditing(false)} />
      )}
    </div>
  );
}

function DealEditModal({
  lead,
  onClose,
}: {
  lead: LeadOut;
  onClose: () => void;
}) {
  const update = useUpdateDealFields(lead.id);
  const [amount, setAmount] = useState<string>(
    lead.deal_amount != null ? String(lead.deal_amount) : "",
  );
  const [quantity, setQuantity] = useState<string>(
    lead.deal_quantity != null ? String(lead.deal_quantity) : "",
  );
  const [equipment, setEquipment] = useState<string>(lead.deal_equipment ?? "");
  const [error, setError] = useState<string | null>(null);

  function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const body: Record<string, unknown> = {};
    // Empty string → null so the field can be cleared from the UI.
    body.deal_amount = amount.trim() === "" ? null : Number(amount);
    if (body.deal_amount !== null && !Number.isFinite(body.deal_amount)) {
      setError("Сумма должна быть числом");
      return;
    }
    body.deal_quantity = quantity.trim() === "" ? null : Number(quantity);
    if (body.deal_quantity !== null && !Number.isInteger(body.deal_quantity)) {
      setError("Количество должно быть целым числом");
      return;
    }
    body.deal_equipment = equipment.trim();

    update.mutate(body, {
      onSuccess: () => onClose(),
      onError: () => setError("Не удалось сохранить"),
    });
  }

  return (
    <Modal open onClose={onClose} title="Детали сделки">
      <form onSubmit={handleSave} className="space-y-3">
        <h2 className="text-base font-bold tracking-tight text-brand-primary">
          Детали сделки
        </h2>

        <label className="block">
          <span className="type-caption font-semibold text-brand-muted">
            Сумма, ₽
          </span>
          <input
            type="number"
            min={0}
            step="1"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="2 400 000"
            className="mt-1 w-full bg-canvas border border-brand-border rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
          />
        </label>

        <div className="flex gap-3">
          <label className="block flex-1">
            <span className="type-caption font-semibold text-brand-muted">
              Количество
            </span>
            <input
              type="number"
              min={0}
              step="1"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder="3"
              className="mt-1 w-full bg-canvas border border-brand-border rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            />
          </label>
          <label className="block flex-1">
            <span className="type-caption font-semibold text-brand-muted">
              Модель
            </span>
            <input
              type="text"
              value={equipment}
              onChange={(e) => setEquipment(e.target.value)}
              placeholder="S100"
              maxLength={50}
              className="mt-1 w-full bg-canvas border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            />
          </label>
        </div>

        {error && <p className="type-caption text-rose">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={update.isPending}
            className="px-4 py-1.5 type-caption font-semibold text-brand-muted hover:text-brand-primary disabled:opacity-40"
          >
            Отмена
          </button>
          <button
            type="submit"
            disabled={update.isPending}
            className="inline-flex items-center gap-1 px-4 py-1.5 type-caption font-semibold bg-brand-accent text-white rounded-full hover:bg-brand-accent/90 disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2"
          >
            {update.isPending && <Loader2 size={11} className="animate-spin" />}
            Сохранить
          </button>
        </div>
      </form>
    </Modal>
  );
}
