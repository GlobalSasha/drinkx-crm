import type { ContactOut, LeadOut, QuoteOut } from "@/lib/types";
import { formatRub } from "@/lib/quote-totals";
import { DrinkXLogo, DrinkXMark } from "@/components/layout/DrinkXLogo";

// Коммерческое предложение как документ — тот же лист, что уходит клиенту.
// Один компонент на вкладку КП и на страницу печати, чтобы менеджер видел
// ровно то, что получит клиент. Данные — плоские, без QuoteOut: так черновик
// показывается «вживую» из формы, до сохранения.

export interface QuoteDocumentLine {
  key: string;
  name: string;
  description: string | null;
  quantity: number;
  unitPrice: number;
  discountPct: number;
  total: number;
}

export interface QuoteDocumentData {
  number: string;
  createdAt: string | null;
  validUntil: string | null;
  companyName: string | null;
  inn: string | null;
  recipientName: string | null;
  recipientTitle: string | null;
  lines: QuoteDocumentLine[];
  subtotal: number;
  discount: number;
  vatRate: number;
  vatAmount: number;
  total: number;
}

export function quoteDocumentData(
  quote: QuoteOut,
  lead: Pick<LeadOut, "company_name" | "inn"> | null | undefined,
  contacts: Pick<ContactOut, "id" | "name" | "title">[],
): QuoteDocumentData {
  const recipient = contacts.find((c) => c.id === quote.recipient_contact_id);
  const afterDiscount = Math.max(quote.subtotal - quote.discount, 0);
  return {
    number: quote.number,
    createdAt: quote.created_at,
    validUntil: quote.valid_until,
    companyName: lead?.company_name ?? null,
    inn: lead?.inn ?? null,
    recipientName: recipient?.name?.trim() || null,
    recipientTitle: recipient?.title ?? null,
    lines: [...quote.lines]
      .sort((a, b) => a.position - b.position)
      .map((l) => ({
        key: l.id,
        name: l.product_name,
        description: l.description,
        quantity: l.quantity,
        unitPrice: l.unit_price,
        discountPct: l.line_discount_pct,
        total: l.total,
      })),
    subtotal: quote.subtotal,
    discount: quote.discount,
    vatRate: quote.vat_rate,
    vatAmount: Math.round((quote.total - afterDiscount) * 100) / 100,
    total: quote.total,
  };
}

// Колонки «Кол-во / Цена / Скидка» — только на широком экране и в печати;
// на телефоне они уходят строкой под наименование.
const WIDE = "hidden sm:table-cell print:table-cell";

function fmtDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function QuoteDocument({
  data,
  className = "",
}: {
  data: QuoteDocumentData;
  className?: string;
}) {
  const created = fmtDate(data.createdAt);
  const validUntil = fmtDate(data.validUntil);

  return (
    <article
      className={`bg-white text-brand-primary rounded-lg shadow-paper p-6 sm:p-8 print:shadow-none print:rounded-none print:p-0 ${className}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4 pb-6 border-b border-brand-border">
        <div>
          <DrinkXLogo className="h-6 w-auto text-brand-primary" />
          <p className="type-caption text-brand-muted mt-2">Умные кофейные станции</p>
        </div>
        <div className="sm:text-right">
          <p className="type-card-title">Коммерческое предложение</p>
          <p className="type-body font-mono text-brand-muted-strong mt-1">{data.number}</p>
          {created && <p className="type-caption text-brand-muted mt-1">от {created}</p>}
        </div>
      </header>

      <section className="py-6 border-b border-brand-border">
        <p className="type-label text-brand-muted">Кому</p>
        <p className="type-card-title mt-1">{data.companyName ?? "—"}</p>
        {data.recipientName && (
          <p className="type-body text-brand-muted-strong mt-0.5">
            {data.recipientName}
            {data.recipientTitle ? `, ${data.recipientTitle}` : ""}
          </p>
        )}
        {data.inn && <p className="type-caption text-brand-muted mt-1">ИНН {data.inn}</p>}
      </section>

      <section className="py-6">
        <table className="w-full type-body tabular-nums border-collapse">
          <thead>
            <tr className="text-left type-label text-brand-muted border-b border-brand-border">
              <th className="py-2 pr-2 font-medium w-6">№</th>
              <th className="py-2 pr-2 font-medium">Наименование</th>
              <th className={`${WIDE} py-2 px-2 font-medium text-right whitespace-nowrap`}>Кол-во</th>
              <th className={`${WIDE} py-2 px-2 font-medium text-right whitespace-nowrap`}>Цена</th>
              <th className={`${WIDE} py-2 px-2 font-medium text-right whitespace-nowrap`}>Скидка</th>
              <th className="py-2 pl-2 font-medium text-right whitespace-nowrap">Сумма</th>
            </tr>
          </thead>
          <tbody>
            {data.lines.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-6 text-center text-brand-muted">
                  Нет позиций
                </td>
              </tr>
            ) : (
              data.lines.map((l, i) => (
                <tr key={l.key} className="border-b border-brand-panel align-top">
                  <td className="py-3 pr-2 text-brand-muted">{i + 1}</td>
                  <td className="py-3 pr-2">
                    <p className="font-medium">{l.name || "Без названия"}</p>
                    {l.description && (
                      <p className="type-caption text-brand-muted mt-0.5">{l.description}</p>
                    )}
                    <p className="sm:hidden print:hidden type-caption text-brand-muted mt-0.5">
                      {l.quantity} × {formatRub(l.unitPrice)}
                      {l.discountPct ? ` · скидка ${l.discountPct}%` : ""}
                    </p>
                  </td>
                  <td className={`${WIDE} py-3 px-2 text-right whitespace-nowrap`}>{l.quantity}</td>
                  <td className={`${WIDE} py-3 px-2 text-right whitespace-nowrap`}>{formatRub(l.unitPrice)}</td>
                  <td className={`${WIDE} py-3 px-2 text-right whitespace-nowrap text-brand-muted`}>
                    {l.discountPct ? `${l.discountPct}%` : "—"}
                  </td>
                  <td className="py-3 pl-2 text-right whitespace-nowrap font-medium">
                    {formatRub(l.total)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      <section className="flex justify-end">
        <dl className="w-full max-w-xs space-y-2 type-body tabular-nums">
          <div className="flex justify-between gap-4">
            <dt className="text-brand-muted">Сумма позиций</dt>
            <dd>{formatRub(data.subtotal)}</dd>
          </div>
          {data.discount > 0 && (
            <div className="flex justify-between gap-4">
              <dt className="text-brand-muted">Скидка</dt>
              <dd>− {formatRub(data.discount)}</dd>
            </div>
          )}
          <div className="flex justify-between gap-4">
            <dt className="text-brand-muted">НДС {data.vatRate}%</dt>
            <dd>+ {formatRub(data.vatAmount)}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-4 border-t border-brand-primary pt-3 mt-1">
            <dt className="type-label">Итого</dt>
            <dd className="type-kpi-number">{formatRub(data.total)}</dd>
          </div>
        </dl>
      </section>

      <footer className="mt-8 pt-4 border-t border-brand-border flex items-center gap-2 type-caption text-brand-muted">
        <DrinkXMark className="w-3 h-3 shrink-0 fill-brand-accent" />
        <span>
          Цены в рублях
          {validUntil ? `. Предложение действует до ${validUntil}` : ""}
        </span>
      </footer>
    </article>
  );
}
