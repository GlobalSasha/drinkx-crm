// Client-side mirror of the server quote-totals formula
// (apps/api/app/quote/services.py · compute_totals). The server stays the
// single source of truth — this only powers the builder's live preview so
// the manager sees totals update before saving. Must match the server math.

export interface LineForTotals {
  quantity: number;
  unit_price: number;
  line_discount_pct: number;
}

export interface QuoteTotals {
  subtotal: number;
  afterDiscount: number;
  vatAmount: number;
  total: number;
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

export function lineTotal(line: LineForTotals): number {
  return round2(
    line.quantity * line.unit_price * (1 - line.line_discount_pct / 100),
  );
}

export function computeQuoteTotals(
  lines: LineForTotals[],
  discount: number,
  vatRate: number,
): QuoteTotals {
  const subtotal = round2(lines.reduce((sum, l) => sum + lineTotal(l), 0));
  const afterDiscount = Math.max(round2(subtotal - discount), 0);
  const vatAmount = round2((afterDiscount * vatRate) / 100);
  const total = round2(afterDiscount + vatAmount);
  return { subtotal, afterDiscount, vatAmount, total };
}

const RUB = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export function formatRub(value: number | string | null | undefined): string {
  if (value == null || value === "") return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return `${RUB.format(n)} ₽`;
}
