import { describe, it, expect } from "vitest";
import { computeQuoteTotals, lineTotal, formatRub } from "./quote-totals";

// Parity with the server formula — apps/api/tests/test_quote_totals.py.
// The server (Decimal, ROUND_HALF_UP) stays authoritative; this client
// mirror only powers the builder's live preview. Sub-kopeck half-up edges
// (e.g. 10.005) can differ under float and are intentionally not asserted.

const line = (quantity: number, unit_price: number, line_discount_pct = 0) => ({
  quantity,
  unit_price,
  line_discount_pct,
});

describe("computeQuoteTotals", () => {
  it("single line, no VAT, no discount", () => {
    const t = computeQuoteTotals([line(2, 100)], 0, 0);
    expect(t.subtotal).toBe(200);
    expect(t.total).toBe(200);
  });

  it("applies a per-line discount percent", () => {
    expect(lineTotal(line(2, 100, 10))).toBe(180); // 2*100*(1-10%)
    const t = computeQuoteTotals([line(2, 100, 10)], 0, 0);
    expect(t.subtotal).toBe(180);
  });

  it("quote discount then VAT", () => {
    // 600 + 400 = 1000; -100 = 900; +20% = 1080
    const t = computeQuoteTotals([line(1, 600), line(1, 400)], 100, 20);
    expect(t.subtotal).toBe(1000);
    expect(t.afterDiscount).toBe(900);
    expect(t.vatAmount).toBe(180);
    expect(t.total).toBe(1080);
  });

  it("clamps a discount larger than the subtotal to zero", () => {
    const t = computeQuoteTotals([line(1, 100)], 500, 20);
    expect(t.subtotal).toBe(100);
    expect(t.afterDiscount).toBe(0);
    expect(t.total).toBe(0);
  });

  it("empty lines total to zero", () => {
    const t = computeQuoteTotals([], 0, 20);
    expect(t.subtotal).toBe(0);
    expect(t.total).toBe(0);
  });
});

describe("formatRub", () => {
  it("formats numbers with a ₽ suffix", () => {
    // Intl uses a narrow no-break space as the group separator — normalise.
    expect(formatRub(1080).replace(/\s/g, " ")).toBe("1 080 ₽");
  });
  it("renders an em dash for empty values", () => {
    expect(formatRub(null)).toBe("—");
    expect(formatRub("")).toBe("—");
  });
});
