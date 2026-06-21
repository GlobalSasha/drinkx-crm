# Quote / КП module (v1)

**Date:** 2026-06-21
**Type:** Feature (new `quote` domain + product catalog + lead-card КП tab)

## Problem

DrinkX sells smart coffee stations, but the CRM has no way to build a commercial
proposal (КП). The `quote/` domain is an empty placeholder; today "КП" is just an
attached file. Managers cannot assemble line items, compute totals, or produce a
client-ready document. PRD §6.6 specifies a Quote builder (entities `quotes` /
`quote_lines`, a КП tab in the lead card, statuses draft/sent/accepted/rejected).
This builds a focused v1 of that.

## Scope (v1) — confirmed with the product owner

- A **«КП»** tab in the lead card: a list of the lead's quotes (number, total,
  status) + a builder for the current draft.
- Line items come from a **DrinkX product catalog OR free-text rows** (mixed).
- Server-computed **totals**: lines − discount + VAT.
- Statuses: draft / sent / accepted / rejected (manual transitions).
- **Output = a print-friendly HTML view the manager saves as PDF** via the
  browser (Ctrl+P → Save as PDF). **No server-side PDF library** (avoids a new
  dependency and deploy risk).
- A **«Сумма сделки = итог КП»** button that copies the quote total to
  `lead.deal_amount` (manual, not automatic).
- VAT is a **per-quote rate**, default **20**, settable to **0** ("без НДС").
- The catalog is **seeded** with a DrinkX starter set (S100, S300, service,
  install, options) at placeholder prices the owner edits later.

## Out of scope (v1)

- Sending the КП by email/messenger from the CRM (the "связь с клиентом" area is
  explicitly deferred). The manager downloads the PDF and sends it themselves.
- AI line-item suggestions (PRD §6.6 mentions them — defer).
- Client-open tracking / shareable public link.
- Real server-rendered PDF, custom branded templates, multi-currency.

## Data model (Alembic migration — three new tables)

Follows PRD §8 data model. All money is `Numeric(12, 2)`; all rows carry
`workspace_id` and are workspace-scoped.

**`products`** (catalog):
- `id` UUID PK, `workspace_id` FK→workspaces (indexed)
- `name` String(160), `category` String(30) (one of: station / service /
  install / option / other), `unit_price` Numeric(12,2) default 0
- `is_active` bool default true, `created_at`, `updated_at`

**`quotes`**:
- `id` UUID PK, `lead_id` FK→leads (CASCADE, indexed), `workspace_id` FK (indexed)
- `number` String(20) — auto `КП-0001`, unique per workspace
- `status` String(12) — draft | sent | accepted | rejected (default draft)
- `recipient_contact_id` FK→contacts (SET NULL, nullable)
- `valid_until` Date (nullable)
- `vat_rate` Numeric(5,2) default 20
- `discount` Numeric(12,2) default 0 — absolute amount off the subtotal
- `subtotal`, `total` Numeric(12,2) — server-computed, stored
- `sent_at`, `accepted_at` DateTime (nullable), `created_by` FK→users (nullable)
- `created_at`, `updated_at`

**`quote_lines`**:
- `id` UUID PK, `quote_id` FK→quotes (CASCADE, indexed)
- `position` int — display order
- `product_id_ref` FK→products (SET NULL, nullable — null = free-text row)
- `product_name` String(200) — denormalized (survives catalog edits/deletes)
- `description` Text (nullable)
- `quantity` Numeric(12,2) default 1, `unit_price` Numeric(12,2) default 0
- `line_discount_pct` Numeric(5,2) default 0 — percent off this line
- `total` Numeric(12,2) — server-computed, stored

### Totals (computed server-side on every quote write — single source of truth)

```
line.total      = round(quantity * unit_price * (1 - line_discount_pct/100), 2)
subtotal        = sum(line.total)
after_discount  = max(subtotal - quote.discount, 0)
vat_amount      = round(after_discount * vat_rate/100, 2)
total           = after_discount + vat_amount
```

Numbering: `КП-{n:04d}` where `n` = (count of quotes in the workspace) + 1,
computed in the same transaction as the insert. Collisions are vanishingly rare
at this scale; a unique `(workspace_id, number)` constraint backstops it (retry
on conflict).

## Backend — `apps/api/app/quote/` (promote the placeholder to a real package)

Package-per-domain: `models.py`, `schemas.py`, `repositories.py`, `services.py`,
`routers.py`. Products live in the same domain (`Product` model + a small
catalog CRUD) — they only exist to serve quotes, so a separate domain is
unwarranted (YAGNI).

Endpoints (all workspace-scoped via `current_user`):
- **Catalog**: `GET /api/products` (list active), `POST /api/products`,
  `PATCH /api/products/{id}`, `DELETE` (soft — `is_active=false`). Create/edit
  gated `require_admin_or_head` (matches forms/settings); list open to all roles.
- **Quotes**: `GET /api/leads/{lead_id}/quotes` (list for a lead),
  `POST /api/leads/{lead_id}/quotes` (create draft, optional initial lines),
  `GET /api/quotes/{id}` (with lines), `PATCH /api/quotes/{id}` (header +
  full line-set replace; recomputes totals), `POST /api/quotes/{id}/status`
  (draft→sent stamps `sent_at`; →accepted stamps `accepted_at`; →rejected),
  `DELETE /api/quotes/{id}` (drafts only), `POST /api/quotes/{id}/apply-to-deal`
  (sets `lead.deal_amount = quote.total`).
- Print data is served by the existing `GET /api/quotes/{id}` — the print view
  is rendered client-side (see Frontend).

Services own: totals computation, number generation, status-transition rules
(can't accept/reject a draft that was never sent? — v1 keeps it permissive:
any manual transition allowed, just stamps timestamps), and workspace isolation.

## Frontend — `apps/web`

- **`components/lead-card/QuoteTab.tsx`** — new lead-card tab «КП» (added to the
  `TABS` array in `LeadCard.tsx` next to Контакты): a list of the lead's quotes
  (number · total · status chip · valid_until) + «Новый КП» button.
- **`components/lead-card/QuoteBuilder.tsx`** (modal or full-tab) — the draft
  builder: recipient (contact picker), valid_until, line table where each row is
  either a catalog pick (search/select a `Product` → fills name + unit_price,
  editable) or a free-text row; quantity, unit_price, line discount %; a
  «+ позиция» add and «+ из каталога»; quote-level discount; VAT toggle
  (20 / 0 / custom); live totals (mirrors the server formula); autosave (debounced
  PATCH); actions «Печать / PDF», «Отметить отправленным», «Дублировать»,
  «Сумма сделки = итог».
- **Print view** — a dedicated route `app/(app)/leads/[id]/quote/[quoteId]/print/page.tsx`
  (or a print-only component) rendering the КП on a clean white A4-ish layout with
  a `@media print` stylesheet; a button calls `window.print()`. The manager saves
  as PDF from the browser dialog. No server PDF.
- **Catalog management** — a minimal products list under Settings (admin/head):
  add/edit/deactivate catalog items. v1 keeps it basic.
- Hooks: `lib/hooks/use-quotes.ts`, `lib/hooks/use-products.ts` (TanStack Query),
  matching the existing hook conventions; `lib/types.ts` gains the DTOs.

## Build phases (one feature, shipped in reviewable slices)

1. **Catalog** — `Product` model + migration + catalog CRUD + seed + settings UI.
2. **Quote backend** — `quotes`/`quote_lines` models + migration + services
   (totals, numbering, status, apply-to-deal) + routers + tests.
3. **Quote builder UI** — КП tab + builder + hooks.
4. **Print view + deal sync** — print route + «Сумма сделки = итог».

Each phase is independently testable and shippable.

## Testing

- **Backend (pytest):** totals math (lines, line %, quote discount, VAT, 0 VAT,
  rounding); number generation (sequential, per-workspace, unique); status
  transitions stamp the right timestamps; `apply-to-deal` sets `deal_amount`;
  workspace isolation (can't read another workspace's quote/product); catalog
  soft-delete. Mirror the mock-only style where DB-free, PG-gated integration
  tests for the repository/number-sequence path.
- **Frontend:** typecheck + lint + `pnpm build`; the builder's client-side totals
  match the server formula; the print route renders a quote.

## Migration & deploy notes

- One Alembic migration adds `products`, `quotes`, `quote_lines` (+ FKs, indexes,
  the `(workspace_id, number)` unique). No changes to existing tables except none
  — `deal_amount` already exists on `leads`.
- No new Python/JS dependency (print-to-PDF is browser-native), so the Docker
  build stays cache-friendly.
- Seed runs idempotently (skip if the workspace already has products).
