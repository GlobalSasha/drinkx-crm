"use client";
import { use } from "react";
import { Printer, ArrowLeft, Loader2 } from "lucide-react";
import { useQuote } from "@/lib/hooks/use-quotes";
import { useLead } from "@/lib/hooks/use-lead";
import { useContacts } from "@/lib/hooks/use-contacts";
import { formatRub } from "@/lib/quote-totals";

// Standalone print view — lives OUTSIDE the (app) route group so it renders
// without the sidebar/shell. The manager opens it, reviews, and saves as PDF
// via the browser print dialog (Ctrl+P). No server-side PDF.

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export default function QuotePrintPage({
  params,
}: {
  params: Promise<{ quoteId: string }>;
}) {
  const { quoteId } = use(params);
  const { data: quote, isLoading, isError } = useQuote(quoteId);
  const { data: lead } = useLead(quote?.lead_id ?? "");
  const { data: contacts = [] } = useContacts(quote?.lead_id ?? "");

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <Loader2 size={22} className="animate-spin text-neutral-400" />
      </div>
    );
  }

  if (isError || !quote) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-white">
        <p className="text-sm text-rose-600">Не удалось загрузить КП</p>
        <button onClick={() => window.close()} className="text-sm text-neutral-500 underline">
          Закрыть
        </button>
      </div>
    );
  }

  const recipient = contacts.find((c) => c.id === quote.recipient_contact_id);
  const afterDiscount = Math.max(quote.subtotal - quote.discount, 0);
  const vatAmount = Math.round((quote.total - afterDiscount) * 100) / 100;
  const sortedLines = [...quote.lines].sort((a, b) => a.position - b.position);

  return (
    <div className="min-h-screen bg-neutral-100 py-8 print:bg-white print:py-0">
      {/* Toolbar — screen only */}
      <div className="max-w-3xl mx-auto mb-4 flex items-center justify-between px-4 print:hidden">
        <button
          onClick={() => window.history.back()}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-neutral-600 hover:text-neutral-900"
        >
          <ArrowLeft size={15} />
          Назад
        </button>
        <button
          onClick={() => window.print()}
          className="inline-flex items-center gap-1.5 rounded-full bg-neutral-900 px-5 py-2 text-sm font-semibold text-white hover:bg-neutral-700"
        >
          <Printer size={15} />
          Печать / Сохранить PDF
        </button>
      </div>

      {/* Document */}
      <article className="max-w-3xl mx-auto bg-white text-neutral-900 p-10 shadow-sm print:shadow-none print:p-0 print:max-w-none">
        <header className="flex items-start justify-between gap-6 border-b border-neutral-200 pb-6">
          <div>
            <p className="text-xl font-extrabold tracking-tight">DrinkX</p>
            <p className="text-xs text-neutral-500 mt-1">Умные кофейные станции</p>
          </div>
          <div className="text-right">
            <p className="text-lg font-bold">Коммерческое предложение</p>
            <p className="text-sm text-neutral-600 mt-0.5">{quote.number}</p>
            <p className="text-xs text-neutral-500 mt-1">от {fmtDate(quote.created_at)}</p>
            {quote.valid_until && (
              <p className="text-xs text-neutral-500">действует до {fmtDate(quote.valid_until)}</p>
            )}
          </div>
        </header>

        {/* Recipient */}
        <section className="py-6 border-b border-neutral-200">
          <p className="text-xs uppercase tracking-wide text-neutral-400">Кому</p>
          <p className="text-base font-semibold mt-1">{lead?.company_name ?? "—"}</p>
          {recipient && (
            <p className="text-sm text-neutral-600">
              {recipient.name}
              {recipient.title ? `, ${recipient.title}` : ""}
            </p>
          )}
          {lead?.inn && <p className="text-xs text-neutral-500 mt-0.5">ИНН {lead.inn}</p>}
        </section>

        {/* Lines */}
        <section className="py-6">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-neutral-400 border-b border-neutral-200">
                <th className="py-2 pr-2 font-medium w-6">№</th>
                <th className="py-2 pr-2 font-medium">Наименование</th>
                <th className="py-2 px-2 font-medium text-right whitespace-nowrap">Кол-во</th>
                <th className="py-2 px-2 font-medium text-right whitespace-nowrap">Цена</th>
                <th className="py-2 px-2 font-medium text-right whitespace-nowrap">Скидка</th>
                <th className="py-2 pl-2 font-medium text-right whitespace-nowrap">Сумма</th>
              </tr>
            </thead>
            <tbody>
              {sortedLines.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-neutral-400">
                    Нет позиций
                  </td>
                </tr>
              ) : (
                sortedLines.map((l, i) => (
                  <tr key={l.id} className="border-b border-neutral-100 align-top">
                    <td className="py-2.5 pr-2 text-neutral-500">{i + 1}</td>
                    <td className="py-2.5 pr-2">
                      <p className="font-medium">{l.product_name}</p>
                      {l.description && (
                        <p className="text-xs text-neutral-500 mt-0.5">{l.description}</p>
                      )}
                    </td>
                    <td className="py-2.5 px-2 text-right whitespace-nowrap">{l.quantity}</td>
                    <td className="py-2.5 px-2 text-right whitespace-nowrap">{formatRub(l.unit_price)}</td>
                    <td className="py-2.5 px-2 text-right whitespace-nowrap">
                      {l.line_discount_pct ? `${l.line_discount_pct}%` : "—"}
                    </td>
                    <td className="py-2.5 pl-2 text-right whitespace-nowrap font-medium">
                      {formatRub(l.total)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>

        {/* Totals */}
        <section className="flex justify-end">
          <div className="w-full max-w-xs space-y-1.5">
            <div className="flex justify-between text-sm">
              <span className="text-neutral-500">Сумма позиций</span>
              <span>{formatRub(quote.subtotal)}</span>
            </div>
            {quote.discount > 0 && (
              <div className="flex justify-between text-sm">
                <span className="text-neutral-500">Скидка</span>
                <span>− {formatRub(quote.discount)}</span>
              </div>
            )}
            <div className="flex justify-between text-sm">
              <span className="text-neutral-500">НДС {quote.vat_rate}%</span>
              <span>+ {formatRub(vatAmount)}</span>
            </div>
            <div className="flex justify-between border-t border-neutral-300 pt-2 mt-1">
              <span className="font-semibold">Итого</span>
              <span className="text-lg font-bold">{formatRub(quote.total)}</span>
            </div>
          </div>
        </section>

        <footer className="mt-12 pt-6 border-t border-neutral-200 text-xs text-neutral-400">
          DrinkX · Коммерческое предложение {quote.number}. Цены указаны в рублях.
        </footer>
      </article>
    </div>
  );
}
