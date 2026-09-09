# Plan 025: Stop conflating rental (monthly) and sale (one-off) amounts in revenue/forecast

> **Executor instructions**: This plan has an OPEN PRODUCT DECISION at the top.
> Do NOT start coding until the decision in "Decision required" is resolved
> (the operator picks an option). Once decided, follow the steps. Honor STOP
> conditions. Update this plan's row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 493a962..HEAD -- apps/api/app/leads/analytics.py apps/api/app/team/repositories.py apps/api/app/leads/models.py`
> Compare against "Current state"; on a mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (touches every money aggregation / dashboard)
- **Depends on**: none
- **Category**: bug (correctness of reported revenue)
- **Planned at**: commit `493a962`, 2026-07-18

## Why this matters

Commit `b62ea04` added a `commercial_model` field (sale vs rental). Per the
model doc, `deal_amount` now means **two incompatible units**: a one-off total
when `commercial_model = 'sale'`, but a **monthly** fee when `= 'rental'`. But
every revenue/forecast aggregation still `SUM(deal_amount)` blindly — so a
10 000 ₽/mo rental is summed identically to a 10 000 ₽ one-off sale. Once
rentals exist in the pipeline, pipeline value, won-revenue by source, and
per-manager totals mix recurring and non-recurring money and stop being a
meaningful total.

## Decision required (resolve BEFORE coding)

How should a rental's monthly `deal_amount` be represented in a total that also
contains one-off sales? Options:

- **(A) Annualize rentals** — count `deal_amount × 12` (or a configurable
  contract length) for rentals in revenue sums. Simple, one branch per SUM.
- **(B) Separate figures** — report "sale revenue" and "rental MRR" as two
  distinct numbers everywhere; never add them into one total.
- **(C) Add a normalized column** — compute a `normalized_amount` (e.g. TCV =
  one-off for sale, monthly×term for rental) at write time and sum that.

Recommended: **(B)** for correctness (never silently add unlike units) with
(A)'s annualized number shown alongside as "annualized rental value" where a
single figure is needed. The operator must pick before Step 1.

## Current state

- `apps/api/app/leads/models.py:126-129` — doc that `deal_amount` is a one-off
  total for sale, monthly fee for rental; the `commercial_model` column added
  by migration `0056`.
- `apps/api/app/leads/analytics.py:31-33` — UTM won-revenue rollup:
  ```python
  func.coalesce(func.sum(case((won, Lead.deal_amount), else_=0)), 0).label("won_sum")
  ```
  No reference to `commercial_model`.
- `apps/api/app/team/repositories.py` — multiple raw-SQL `SUM(deal_amount)`
  with no model branch: `:253` (`workload_rows` `sum_amount`), `:310`
  (`portfolio_kpi` `total_amount`), `:312` (`avg_amount`), `:316`
  (`at_risk_amount`), `:327` (`portfolio_by_segment`), `:339`
  (`portfolio_by_stage`), `:350` (`portfolio_by_priority`), `:361`/`:363`
  (`portfolio_top_deals`).
- Also check `apps/api/app/leads/analytics.py` stage-dwell/forecast helpers and
  any `forecast` service (`grep -rn "deal_amount" apps/api/app`) — enumerate ALL
  SUM sites before changing any, so none is missed.

## Commands you will need

| Purpose        | Command                                                       | Expected on success |
|----------------|---------------------------------------------------------------|---------------------|
| Enumerate sums | `grep -rn "deal_amount" apps/api/app`                         | full list to cover  |
| Compile check  | `cd apps/api && python -m py_compile app/leads/analytics.py app/team/repositories.py` | exit 0 |
| Analytics tests| `cd apps/api && uv run pytest -q tests/ -k "analytics or team or forecast or utm"` | all pass |

## Scope

**In scope** (depends on the chosen option):
- `apps/api/app/leads/analytics.py`
- `apps/api/app/team/repositories.py`
- Any forecast service found by the grep
- Frontend labels IF option (B): the dashboards that render these totals must
  label sale vs rental separately (`apps/web` — enumerate from the API
  consumers; out of scope until the API returns the split)
- Tests for the changed aggregations

**Out of scope**:
- The `commercial_model` column/migration itself (already shipped).
- Changing what `deal_amount` stores (keep monthly-for-rental; normalize in
  queries or a derived column, not by rewriting inputs) unless option (C) is
  chosen and explicitly approved.

## Steps (after the decision)

### Step 1: Enumerate every `deal_amount` aggregation

Run the grep; make a checklist of every SUM/AVG site. Each must be updated
consistently per the chosen option. Missing one reintroduces the mixing.

**Verify**: the checklist covers every hit from `grep -rn "deal_amount" apps/api/app`.

### Step 2: Apply the chosen normalization

- **Option A**: branch each SUM: `SUM(CASE WHEN commercial_model='rental' THEN deal_amount*12 ELSE deal_amount END)`.
- **Option B**: split each aggregate into `sale_sum` (WHERE model='sale') and
  `rental_mrr` (WHERE model='rental'); update the response schemas and the
  frontend labels. This is the larger change but the correct one.
- **Option C**: add `normalized_amount` (computed column or app-set on
  deal save) + migration; sum that.

**Verify**: `python -m py_compile ...` → exit 0.

### Step 3: Tests

Add tests asserting that a workspace with one 10 000 sale and one 10 000/mo
rental reports the numbers correctly under the chosen model (e.g. option B:
sale_sum=10 000, rental_mrr=10 000, never a single 20 000 "revenue").

**Verify**: `uv run pytest -q tests/ -k "analytics or team or forecast"` → pass.

## Done criteria

- [ ] The product decision is recorded in this plan's Status/PR
- [ ] Every `deal_amount` aggregation from the grep is updated consistently
- [ ] `python -m py_compile` on touched files exits 0
- [ ] Tests assert sale/rental are not blindly summed as one unit
- [ ] If option B: API response schemas + frontend labels updated
- [ ] `plans/README.md` status row updated

## STOP conditions

- The decision is not made — do not pick a unit yourself; STOP and ask.
- The grep reveals `deal_amount` SUMs in modules not listed here (e.g. a
  reporting/export path) — add them to scope and note it, don't skip them.

## Maintenance notes

- Any NEW money aggregation must respect `commercial_model` — add a shared SQL
  fragment or a helper so the next one can't forget.
- Reviewer: confirm no single figure adds sale + rental of different units.
- If contract length becomes configurable, option A's ×12 must read that.
