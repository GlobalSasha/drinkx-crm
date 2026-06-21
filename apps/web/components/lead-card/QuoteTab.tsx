"use client";
import { useState } from "react";
import { Plus, FileText, Loader2, ChevronRight } from "lucide-react";
import { useLeadQuotes, useCreateQuote } from "@/lib/hooks/use-quotes";
import type { LeadOut, QuoteListItemOut, QuoteStatus } from "@/lib/types";
import { C } from "@/lib/design-system";
import { formatRub } from "@/lib/quote-totals";
import { Badge } from "@/components/ui/Badge";
import { QuoteBuilder } from "./QuoteBuilder";

type StatusVariant = "neutral" | "accent" | "success" | "rose";

export const QUOTE_STATUS_META: Record<
  QuoteStatus,
  { label: string; variant: StatusVariant }
> = {
  draft: { label: "Черновик", variant: "neutral" },
  sent: { label: "Отправлено", variant: "accent" },
  accepted: { label: "Принято", variant: "success" },
  rejected: { label: "Отклонено", variant: "rose" },
};

function formatValidUntil(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `до ${d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}`;
}

interface Props {
  lead: LeadOut;
}

export function QuoteTab({ lead }: Props) {
  const { data: quotes = [], isLoading } = useLeadQuotes(lead.id);
  const createQuote = useCreateQuote(lead.id);
  const [openQuoteId, setOpenQuoteId] = useState<string | null>(null);

  if (openQuoteId) {
    return (
      <QuoteBuilder
        leadId={lead.id}
        quoteId={openQuoteId}
        onClose={() => setOpenQuoteId(null)}
      />
    );
  }

  function handleCreate() {
    if (createQuote.isPending) return;
    createQuote.mutate({}, { onSuccess: (q) => setOpenQuoteId(q.id) });
  }

  if (isLoading) {
    return (
      <div className={`py-8 text-center type-caption ${C.color.muted}`}>
        Загрузка КП…
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className={`type-caption ${C.color.muted}`}>
          Коммерческие предложения · {quotes.length}
        </p>
        <button
          type="button"
          onClick={handleCreate}
          disabled={createQuote.isPending}
          className={`inline-flex items-center gap-1.5 px-4 py-1.5 type-body font-semibold text-white ${C.button.primary} disabled:opacity-50`}
        >
          {createQuote.isPending ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Plus size={13} />
          )}
          Новый КП
        </button>
      </div>

      {quotes.length === 0 ? (
        <div className="rounded-card border border-dashed border-brand-border bg-white px-4 py-10 text-center">
          <FileText size={22} className="mx-auto text-brand-muted" />
          <p className="type-caption text-brand-muted mt-2.5">
            Пока нет ни одного КП. Создайте первый — соберите позиции из
            каталога или вручную.
          </p>
        </div>
      ) : (
        <ul className="space-y-2.5">
          {quotes.map((q) => (
            <QuoteRow key={q.id} quote={q} onOpen={() => setOpenQuoteId(q.id)} />
          ))}
        </ul>
      )}
    </div>
  );
}

function QuoteRow({
  quote,
  onOpen,
}: {
  quote: QuoteListItemOut;
  onOpen: () => void;
}) {
  const meta = QUOTE_STATUS_META[quote.status] ?? QUOTE_STATUS_META.draft;
  const validUntil = formatValidUntil(quote.valid_until);

  return (
    <li
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className={`flex items-center gap-3 rounded-card border border-brand-border bg-white p-3.5 cursor-pointer transition-colors hover:border-brand-accent ${C.focusRing}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className={`type-caption font-semibold ${C.color.text}`}>
            {quote.number}
          </p>
          <Badge variant={meta.variant}>{meta.label}</Badge>
          {validUntil && (
            <span className="type-hint text-brand-muted">{validUntil}</span>
          )}
        </div>
        <p className={`type-card-title mt-1 ${C.color.text}`}>
          {formatRub(quote.total)}
        </p>
      </div>
      <ChevronRight size={16} className="text-brand-muted shrink-0" />
    </li>
  );
}
