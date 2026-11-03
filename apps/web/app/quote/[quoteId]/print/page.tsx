"use client";
import { use } from "react";
import { Printer, ArrowLeft, Loader2 } from "lucide-react";
import { useQuote } from "@/lib/hooks/use-quotes";
import { useLead } from "@/lib/hooks/use-lead";
import { useContacts } from "@/lib/hooks/use-contacts";
import { QuoteDocument, quoteDocumentData } from "@/components/lead-card/QuoteDocument";

// Standalone print view — lives OUTSIDE the (app) route group so it renders
// without the sidebar/shell. The manager opens it, reviews, and saves as PDF
// via the browser print dialog (Ctrl+P). No server-side PDF.

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

  return (
    <div className="min-h-screen bg-brand-bg py-8 print:bg-white print:py-0">
      {/* Toolbar — screen only */}
      <div className="max-w-3xl mx-auto mb-4 flex items-center justify-between px-4 print:hidden">
        <button
          onClick={() => window.history.back()}
          className="inline-flex items-center gap-1.5 type-button text-brand-muted hover:text-brand-primary"
        >
          <ArrowLeft size={15} />
          Назад
        </button>
        <button
          onClick={() => window.print()}
          className="inline-flex items-center gap-1.5 rounded-full bg-brand-primary px-5 py-2 type-button text-white hover:bg-brand-muted-strong"
        >
          <Printer size={15} />
          Печать / Сохранить PDF
        </button>
      </div>

      <QuoteDocument
        data={quoteDocumentData(quote, lead, contacts)}
        className="max-w-3xl mx-auto print:max-w-none"
      />
    </div>
  );
}
