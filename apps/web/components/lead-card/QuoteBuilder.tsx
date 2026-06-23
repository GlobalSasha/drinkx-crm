"use client";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Plus,
  Trash2,
  Loader2,
  AlertTriangle,
  Check,
  Printer,
  Wallet,
} from "lucide-react";
import {
  useQuote,
  useUpdateQuote,
  useSetQuoteStatus,
  useDeleteQuote,
  useApplyToDeal,
} from "@/lib/hooks/use-quotes";
import { useContacts } from "@/lib/hooks/use-contacts";
import { useProducts } from "@/lib/hooks/use-products";
import type { ProductOut, QuoteOut, QuoteUpdate } from "@/lib/types";
import { C } from "@/lib/design-system";
import { computeQuoteTotals, formatRub } from "@/lib/quote-totals";
import { Badge } from "@/components/ui/Badge";
import { QUOTE_STATUS_META } from "./QuoteTab";

// Local edit row — numeric fields are kept as strings so inputs stay
// controlled while the manager types (parsed via num() on compute/save).
interface EditLine {
  uid: string;
  product_id_ref: string | null;
  product_name: string;
  description: string;
  quantity: string;
  unit_price: string;
  line_discount_pct: string;
}

interface FormState {
  id: string;
  recipient_contact_id: string;
  valid_until: string;
  vat_rate: string;
  discount: string;
  lines: EditLine[];
}

let uidCounter = 0;
const nextUid = () => `l${++uidCounter}`;

const num = (s: string): number => {
  const n = Number(String(s).replace(",", "."));
  return Number.isFinite(n) ? n : 0;
};

function toForm(q: QuoteOut): FormState {
  return {
    id: q.id,
    recipient_contact_id: q.recipient_contact_id ?? "",
    valid_until: q.valid_until ?? "",
    vat_rate: String(q.vat_rate ?? 20),
    discount: String(q.discount ?? 0),
    lines: [...q.lines]
      .sort((a, b) => a.position - b.position)
      .map((l) => ({
        uid: nextUid(),
        product_id_ref: l.product_id_ref,
        product_name: l.product_name,
        description: l.description ?? "",
        quantity: String(l.quantity),
        unit_price: String(l.unit_price),
        line_discount_pct: String(l.line_discount_pct),
      })),
  };
}

const fieldCls =
  "w-full bg-white border border-brand-border rounded-lg px-2.5 py-1.5 type-body text-brand-primary outline-none focus:border-brand-accent transition-colors disabled:opacity-70";

interface Props {
  leadId: string;
  quoteId: string;
  onClose: () => void;
}

export function QuoteBuilder({ leadId, quoteId, onClose }: Props) {
  const { data: quote, isLoading, isError } = useQuote(quoteId);
  const { data: contacts = [] } = useContacts(leadId);
  const { data: products = [] } = useProducts();
  const update = useUpdateQuote(leadId, quoteId);
  const setStatus = useSetQuoteStatus(leadId, quoteId);
  const del = useDeleteQuote(leadId);
  const applyToDeal = useApplyToDeal(leadId, quoteId);

  const [form, setForm] = useState<FormState | null>(null);
  const [dirty, setDirty] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [dealApplied, setDealApplied] = useState(false);

  useEffect(() => {
    if (quote && (!form || form.id !== quote.id)) {
      setForm(toForm(quote));
      setDirty(false);
    }
  }, [quote, form]);

  const editable = quote?.status === "draft";

  const totals = useMemo(() => {
    if (!form) return null;
    return computeQuoteTotals(
      form.lines.map((l) => ({
        quantity: num(l.quantity),
        unit_price: num(l.unit_price),
        line_discount_pct: num(l.line_discount_pct),
      })),
      num(form.discount),
      num(form.vat_rate),
    );
  }, [form]);

  if (isLoading || !form) {
    return (
      <div className="py-10 flex justify-center">
        <Loader2 size={20} className="animate-spin text-brand-muted" />
      </div>
    );
  }

  if (isError || !quote) {
    return (
      <div className="py-10 flex flex-col items-center gap-3">
        <AlertTriangle size={20} className="text-rose" />
        <p className="type-caption text-rose">Не удалось загрузить КП</p>
        <button type="button" onClick={onClose} className={`type-caption ${C.color.accent}`}>
          ← Назад к списку
        </button>
      </div>
    );
  }

  const meta = QUOTE_STATUS_META[quote.status] ?? QUOTE_STATUS_META.draft;

  function patchForm(p: Partial<FormState>) {
    setForm((f) => (f ? { ...f, ...p } : f));
    setDirty(true);
  }

  function patchLine(uid: string, p: Partial<EditLine>) {
    setForm((f) =>
      f ? { ...f, lines: f.lines.map((l) => (l.uid === uid ? { ...l, ...p } : l)) } : f,
    );
    setDirty(true);
  }

  function addBlankLine() {
    setForm((f) =>
      f
        ? {
            ...f,
            lines: [
              ...f.lines,
              {
                uid: nextUid(),
                product_id_ref: null,
                product_name: "",
                description: "",
                quantity: "1",
                unit_price: "0",
                line_discount_pct: "0",
              },
            ],
          }
        : f,
    );
    setDirty(true);
  }

  function addCatalogLine(product: ProductOut) {
    setForm((f) =>
      f
        ? {
            ...f,
            lines: [
              ...f.lines,
              {
                uid: nextUid(),
                product_id_ref: product.id,
                product_name: product.name,
                description: "",
                quantity: "1",
                unit_price: String(product.unit_price),
                line_discount_pct: "0",
              },
            ],
          }
        : f,
    );
    setDirty(true);
  }

  function removeLine(uid: string) {
    setForm((f) => (f ? { ...f, lines: f.lines.filter((l) => l.uid !== uid) } : f));
    setDirty(true);
  }

  function handleSave() {
    if (!form) return;
    const body: QuoteUpdate = {
      recipient_contact_id: form.recipient_contact_id || null,
      valid_until: form.valid_until || null,
      vat_rate: num(form.vat_rate),
      discount: num(form.discount),
      lines: form.lines
        .filter((l) => l.product_name.trim())
        .map((l) => ({
          product_id_ref: l.product_id_ref,
          product_name: l.product_name.trim(),
          description: l.description.trim() || null,
          quantity: num(l.quantity),
          unit_price: num(l.unit_price),
          line_discount_pct: num(l.line_discount_pct),
        })),
    };
    update.mutate(body, { onSuccess: () => setDirty(false) });
  }

  function handleBack() {
    if (dirty && !window.confirm("Есть несохранённые изменения. Выйти без сохранения?")) {
      return;
    }
    onClose();
  }

  function openPrint() {
    if (
      dirty &&
      !window.confirm(
        "Есть несохранённые изменения — печать покажет последнюю сохранённую версию. Продолжить?",
      )
    ) {
      return;
    }
    window.open(`/quote/${quoteId}/print`, "_blank", "noopener");
  }

  function applyDeal() {
    if (
      dirty &&
      !window.confirm(
        "Сначала сохраните КП — в сделку запишется последний сохранённый итог. Продолжить?",
      )
    ) {
      return;
    }
    applyToDeal.mutate(undefined, {
      onSuccess: () => {
        setDealApplied(true);
        setTimeout(() => setDealApplied(false), 2500);
      },
    });
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={handleBack}
          className={`inline-flex items-center gap-1.5 type-caption font-semibold ${C.color.muted} hover:${C.color.text} transition-colors`}
        >
          <ArrowLeft size={14} />
          К списку
        </button>
        <div className="flex items-center gap-2">
          <span className={`type-caption font-semibold ${C.color.text}`}>{quote.number}</span>
          <Badge variant={meta.variant}>{meta.label}</Badge>
        </div>
      </div>

      {!editable && (
        <p className="type-hint text-brand-muted bg-brand-panel rounded-card px-3.5 py-2.5">
          КП уже отправлено — позиции зафиксированы. Доступна только смена статуса.
        </p>
      )}

      {/* Header fields */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="space-y-1">
          <span className={C.form.label}>Получатель</span>
          <select
            value={form.recipient_contact_id}
            onChange={(e) => patchForm({ recipient_contact_id: e.target.value })}
            disabled={!editable}
            className={fieldCls}
          >
            <option value="">— не выбран —</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name?.trim() || "Без имени"}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className={C.form.label}>Действует до</span>
          <input
            type="date"
            value={form.valid_until}
            onChange={(e) => patchForm({ valid_until: e.target.value })}
            disabled={!editable}
            className={fieldCls}
          />
        </label>
      </div>

      {/* Lines */}
      <div className="space-y-2.5">
        <span className={C.form.label}>Позиции</span>
        {form.lines.length === 0 && (
          <p className="type-hint text-brand-muted py-3 text-center rounded-card border border-dashed border-brand-border">
            Ни одной позиции. Добавьте из каталога или вручную.
          </p>
        )}
        {form.lines.map((line) => (
          <LineEditor
            key={line.uid}
            line={line}
            editable={!!editable}
            onChange={(p) => patchLine(line.uid, p)}
            onRemove={() => removeLine(line.uid)}
          />
        ))}

        {editable && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={addBlankLine}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 type-body font-semibold ${C.button.ghost}`}
            >
              <Plus size={13} />
              Позиция
            </button>
            {products.length > 0 && (
              <select
                value=""
                onChange={(e) => {
                  const p = products.find((x) => x.id === e.target.value);
                  if (p) addCatalogLine(p);
                }}
                className={`${fieldCls} w-auto max-w-[16rem] rounded-full`}
                aria-label="Добавить из каталога"
              >
                <option value="">+ из каталога</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {formatRub(p.unit_price)}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}
      </div>

      {/* Discount + VAT */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="space-y-1">
          <span className={C.form.label}>Скидка на КП, ₽</span>
          <input
            value={form.discount}
            onChange={(e) => patchForm({ discount: e.target.value })}
            disabled={!editable}
            inputMode="decimal"
            className={fieldCls}
          />
        </label>
        <div className="space-y-1">
          <span className={C.form.label}>НДС</span>
          <div className="flex items-center gap-2">
            <VatPill active={num(form.vat_rate) === 20} editable={!!editable} onClick={() => patchForm({ vat_rate: "20" })}>
              20%
            </VatPill>
            <VatPill active={num(form.vat_rate) === 0} editable={!!editable} onClick={() => patchForm({ vat_rate: "0" })}>
              Без НДС
            </VatPill>
            <input
              value={form.vat_rate}
              onChange={(e) => patchForm({ vat_rate: e.target.value })}
              disabled={!editable}
              inputMode="decimal"
              aria-label="Ставка НДС, %"
              className={`${fieldCls} w-20`}
            />
            <span className="type-caption text-brand-muted">%</span>
          </div>
        </div>
      </div>

      {/* Totals */}
      {totals && (
        <div className="rounded-card border border-brand-border bg-brand-panel p-4 space-y-1.5">
          <TotalRow label="Сумма позиций" value={formatRub(totals.subtotal)} />
          {num(form.discount) > 0 && (
            <TotalRow label="Скидка" value={`− ${formatRub(num(form.discount))}`} />
          )}
          <TotalRow label={`НДС ${num(form.vat_rate)}%`} value={`+ ${formatRub(totals.vatAmount)}`} />
          <div className="border-t border-brand-border pt-2 mt-1 flex items-center justify-between">
            <span className={`type-caption font-semibold ${C.color.text}`}>Итого</span>
            <span className={`type-card-title ${C.color.text} tabular-nums`}>{formatRub(totals.total)}</span>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {editable && (
          <>
            <button
              type="button"
              onClick={handleSave}
              disabled={!dirty || update.isPending}
              className={`inline-flex items-center gap-1.5 px-4 py-2 type-body font-semibold text-white ${C.button.primary} disabled:opacity-50`}
            >
              {update.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : !dirty ? (
                <Check size={14} />
              ) : null}
              {update.isPending ? "Сохранение…" : dirty ? "Сохранить" : "Сохранено"}
            </button>
            <button
              type="button"
              onClick={() => {
                if (dirty) {
                  if (!window.confirm("Сначала сохраните изменения. Отметить отправленным без сохранения?")) return;
                }
                setStatus.mutate("sent");
              }}
              disabled={setStatus.isPending}
              className={`inline-flex items-center gap-1.5 px-4 py-2 type-body font-semibold ${C.button.ghost} disabled:opacity-50`}
            >
              Отметить отправленным
            </button>
          </>
        )}

        {quote.status === "sent" && (
          <>
            <button
              type="button"
              onClick={() => setStatus.mutate("accepted")}
              disabled={setStatus.isPending}
              className={`inline-flex items-center gap-1.5 px-4 py-2 type-body font-semibold text-white ${C.button.primary} disabled:opacity-50`}
            >
              Принято
            </button>
            <button
              type="button"
              onClick={() => setStatus.mutate("rejected")}
              disabled={setStatus.isPending}
              className={`inline-flex items-center gap-1.5 px-4 py-2 type-body font-semibold ${C.button.ghost} disabled:opacity-50`}
            >
              Отклонено
            </button>
          </>
        )}

        {/* Document actions — available for any status */}
        <button
          type="button"
          onClick={openPrint}
          className={`inline-flex items-center gap-1.5 px-4 py-2 type-body font-semibold ${C.button.ghost}`}
        >
          <Printer size={14} />
          Печать / PDF
        </button>
        <button
          type="button"
          onClick={applyDeal}
          disabled={applyToDeal.isPending}
          className={`inline-flex items-center gap-1.5 px-4 py-2 type-body font-semibold ${C.button.ghost} disabled:opacity-50`}
        >
          {applyToDeal.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : dealApplied ? (
            <Check size={14} className="text-success" />
          ) : (
            <Wallet size={14} />
          )}
          {dealApplied ? "Применено" : "Сумма сделки = итог"}
        </button>

        {editable && (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            className="ml-auto inline-flex items-center gap-1.5 px-3 py-2 type-caption font-semibold text-brand-muted hover:text-rose transition-colors"
          >
            <Trash2 size={13} />
            Удалить
          </button>
        )}
      </div>

      {confirmDelete && (
        <div className="rounded-card border border-rose/30 bg-rose/5 p-4 space-y-3">
          <p className="type-caption text-brand-primary">
            Удалить черновик {quote.number}? Действие необратимо.
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => del.mutate(quoteId, { onSuccess: onClose })}
              disabled={del.isPending}
              className="px-4 py-1.5 type-caption font-semibold text-white bg-rose rounded-full disabled:opacity-50"
            >
              {del.isPending ? "Удаление…" : "Удалить"}
            </button>
            <button
              type="button"
              onClick={() => setConfirmDelete(false)}
              className={`px-4 py-1.5 type-caption font-semibold ${C.button.ghost}`}
            >
              Отмена
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function LineEditor({
  line,
  editable,
  onChange,
  onRemove,
}: {
  line: EditLine;
  editable: boolean;
  onChange: (p: Partial<EditLine>) => void;
  onRemove: () => void;
}) {
  const total =
    num(line.quantity) * num(line.unit_price) * (1 - num(line.line_discount_pct) / 100);

  return (
    <div className="rounded-card border border-brand-border bg-white p-3 space-y-2.5">
      <div className="flex items-start gap-2">
        <input
          value={line.product_name}
          onChange={(e) => onChange({ product_name: e.target.value })}
          disabled={!editable}
          placeholder="Название позиции"
          className={`${fieldCls} font-medium`}
        />
        {editable && (
          <button
            type="button"
            onClick={onRemove}
            aria-label="Убрать позицию"
            className="shrink-0 p-2 text-brand-muted hover:text-rose transition-colors"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
      <input
        value={line.description}
        onChange={(e) => onChange({ description: e.target.value })}
        disabled={!editable}
        placeholder="Описание (необязательно)"
        className={`${fieldCls} type-caption`}
      />
      <div className="grid grid-cols-3 gap-2">
        <label className="space-y-1">
          <span className="type-hint text-brand-muted">Кол-во</span>
          <input
            value={line.quantity}
            onChange={(e) => onChange({ quantity: e.target.value })}
            disabled={!editable}
            inputMode="decimal"
            className={fieldCls}
          />
        </label>
        <label className="space-y-1">
          <span className="type-hint text-brand-muted">Цена, ₽</span>
          <input
            value={line.unit_price}
            onChange={(e) => onChange({ unit_price: e.target.value })}
            disabled={!editable}
            inputMode="decimal"
            className={fieldCls}
          />
        </label>
        <label className="space-y-1">
          <span className="type-hint text-brand-muted">Скидка, %</span>
          <input
            value={line.line_discount_pct}
            onChange={(e) => onChange({ line_discount_pct: e.target.value })}
            disabled={!editable}
            inputMode="decimal"
            className={fieldCls}
          />
        </label>
      </div>
      <div className="flex items-center justify-end gap-1.5">
        <span className="type-hint text-brand-muted">Итого по позиции:</span>
        <span className="type-caption font-semibold text-brand-primary tabular-nums">
          {formatRub(total)}
        </span>
      </div>
    </div>
  );
}

function VatPill({
  active,
  editable,
  onClick,
  children,
}: {
  active: boolean;
  editable: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!editable}
      className={`px-3 py-1.5 type-caption font-semibold rounded-full border transition-colors disabled:opacity-60 ${
        active
          ? "bg-brand-accent text-white border-brand-accent"
          : "bg-white text-brand-muted-strong border-brand-border hover:border-brand-accent"
      }`}
    >
      {children}
    </button>
  );
}

function TotalRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="type-caption text-brand-muted">{label}</span>
      <span className="type-caption text-brand-primary tabular-nums">{value}</span>
    </div>
  );
}
