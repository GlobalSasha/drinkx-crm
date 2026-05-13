# Sprint 3.5 — Segment Enum + Leads Pool Filters

## Context

Two data quality problems blocking usable filtering:
1. `leads.segment` is free text — same company type written differently by different people
2. `leads.city` is free text — no normalization

Three UX problems in `/leads-pool`:
1. No click-through to lead card
2. No search or filters
3. City column always shows "—" (data empty or not displayed)

This sprint fixes all five.

---

## ADR-023 — Segment = controlled vocabulary, not DB enum

**Decision:** `leads.segment` stays VARCHAR(50) in DB (no ALTER TYPE),
but the application enforces a fixed list of 8 values.

**Why not DB ENUM:** Adding a new segment later requires a migration with table lock.
VARCHAR + app-level validation is safer and fast enough.

**Canonical segment values (English keys, Russian labels):**
```python
SEGMENT_CHOICES = [
    ("retail_food",     "Продуктовый ритейл"),
    ("retail_nonfood",  "Непродуктовый ритейл"),
    ("cafe_restaurant", "Кофейни / Кафе / Рестораны"),
    ("qsr",             "QSR / Fast Food"),
    ("petrol",          "АЗС"),
    ("office",          "Офисы"),
    ("hotel",           "Отели"),
    ("distributor",     "Дистрибьюторы"),
]
```

Record in `docs/brain/03_DECISIONS.md`.

---

## G1 — Backend: segment validation + city normalization

### `app/leads/constants.py` (new file)

```python
SEGMENT_CHOICES = [
    ("retail_food",     "Продуктовый ритейл"),
    ("retail_nonfood",  "Непродуктовый ритейл"),
    ("cafe_restaurant", "Кофейни / Кафе / Рестораны"),
    ("qsr",             "QSR / Fast Food"),
    ("petrol",          "АЗС"),
    ("office",          "Офисы"),
    ("hotel",           "Отели"),
    ("distributor",     "Дистрибьюторы"),
]

SEGMENT_KEYS = [s[0] for s in SEGMENT_CHOICES]

# City normalization helper
import re

def normalize_city(city: str | None) -> str | None:
    if not city:
        return None
    s = city.strip()
    # Remove "г.", "г " prefix
    s = re.sub(r'^г\.?\s*', '', s, flags=re.IGNORECASE)
    # Capitalize first letter
    s = s.strip().capitalize()
    return s or None
```

### `app/leads/schemas.py` — add validation

In `LeadCreate` and `LeadUpdate` Pydantic models:
```python
from app.leads.constants import SEGMENT_KEYS, normalize_city

@validator('segment')
def validate_segment(cls, v):
    if v is not None and v not in SEGMENT_KEYS:
        raise ValueError(f'Invalid segment. Must be one of: {SEGMENT_KEYS}')
    return v

@validator('city')
def validate_city(cls, v):
    return normalize_city(v)
```

### New endpoint: `GET /api/leads/cities`

Returns distinct normalized cities for autocomplete:
```sql
SELECT DISTINCT normalize_city_func(city) AS city
FROM leads
WHERE workspace_id = :wid
  AND city IS NOT NULL AND city != ''
ORDER BY city ASC
```

Note: normalization happens in Python after fetch (reuse `normalize_city()`), not in SQL.

Response: `{ "cities": ["Екатеринбург", "Москва", "Новосибирск", ...] }`

### Updated `GET /api/leads/pool`

Add filter params:
- `segment` — one of SEGMENT_KEYS
- `city` — string (ILIKE match against normalized city)
- `priority` — A / B / C / D
- `fit_score_min` — integer 0–10
- `q` — search by company_name (ILIKE)

```python
# repositories.py — add to pool query
if filters.segment:
    query = query.filter(Lead.segment == filters.segment)
if filters.city:
    query = query.filter(Lead.city.ilike(f"%{filters.city}%"))
if filters.priority:
    query = query.filter(Lead.priority == filters.priority)
if filters.fit_score_min is not None:
    query = query.filter(Lead.fit_score >= filters.fit_score_min)
if filters.q:
    query = query.filter(Lead.company_name.ilike(f"%{filters.q}%"))
```

---

## G2 — Data migration (Alembic 0025)

### Migration goal
1. Normalize existing `leads.city` values
2. Map existing `leads.segment` free-text values to new keys
3. Do the same for `companies.primary_segment`

### Migration file `0025_normalize_segment_city`

```sql
-- Step 1: normalize city (strip "г.", capitalize — done in Python upgrade())
-- Step 2: map segment values

UPDATE leads SET segment = CASE
    WHEN lower(segment) ILIKE '%продуктов%'                   THEN 'retail_food'
    WHEN lower(segment) ILIKE '%непродуктов%'
      OR lower(segment) ILIKE '%нонфуд%'
      OR lower(segment) ILIKE '%non%food%'                    THEN 'retail_nonfood'
    WHEN lower(segment) ILIKE '%кофейн%'
      OR lower(segment) ILIKE '%кафе%'
      OR lower(segment) ILIKE '%ресторан%'
      OR lower(segment) ILIKE '%horeca%'
      OR lower(segment) ILIKE '%хорека%'                      THEN 'cafe_restaurant'
    WHEN lower(segment) ILIKE '%qsr%'
      OR lower(segment) ILIKE '%fast%food%'
      OR lower(segment) ILIKE '%фастфуд%'                     THEN 'qsr'
    WHEN lower(segment) ILIKE '%азс%'
      OR lower(segment) ILIKE '%заправ%'
      OR lower(segment) ILIKE '%petrol%'                      THEN 'petrol'
    WHEN lower(segment) ILIKE '%офис%'
      OR lower(segment) ILIKE '%office%'                      THEN 'office'
    WHEN lower(segment) ILIKE '%отел%'
      OR lower(segment) ILIKE '%hotel%'                       THEN 'hotel'
    WHEN lower(segment) ILIKE '%дистриб%'
      OR lower(segment) ILIKE '%distributor%'                 THEN 'distributor'
    ELSE segment  -- keep unknown values, surface in report
END
WHERE workspace_id IS NOT NULL;

-- Same for companies.primary_segment
UPDATE companies SET primary_segment = CASE
    WHEN lower(primary_segment) ILIKE '%продуктов%'           THEN 'retail_food'
    WHEN lower(primary_segment) ILIKE '%непродуктов%'
      OR lower(primary_segment) ILIKE '%нонфуд%'              THEN 'retail_nonfood'
    WHEN lower(primary_segment) ILIKE '%кофейн%'
      OR lower(primary_segment) ILIKE '%кафе%'
      OR lower(primary_segment) ILIKE '%ресторан%'
      OR lower(primary_segment) ILIKE '%horeca%'              THEN 'cafe_restaurant'
    WHEN lower(primary_segment) ILIKE '%qsr%'
      OR lower(primary_segment) ILIKE '%fast%'                THEN 'qsr'
    WHEN lower(primary_segment) ILIKE '%азс%'                 THEN 'petrol'
    WHEN lower(primary_segment) ILIKE '%офис%'                THEN 'office'
    WHEN lower(primary_segment) ILIKE '%отел%'                THEN 'hotel'
    WHEN lower(primary_segment) ILIKE '%дистриб%'             THEN 'distributor'
    ELSE primary_segment
END
WHERE workspace_id IS NOT NULL;
```

Python `upgrade()` also runs city normalization:
```python
# In upgrade() function:
conn = op.get_bind()
rows = conn.execute(text("SELECT id, city FROM leads WHERE city IS NOT NULL"))
for row in rows:
    normalized = normalize_city(row.city)
    if normalized != row.city:
        conn.execute(
            text("UPDATE leads SET city = :c WHERE id = :id"),
            {"c": normalized, "id": row.id}
        )
```

### Post-migration report (print in upgrade())
```
Segment mapping report:
  retail_food:     N leads
  retail_nonfood:  N leads
  cafe_restaurant: N leads
  qsr:             N leads
  petrol:          N leads
  office:          N leads
  hotel:           N leads
  distributor:     N leads
  UNMAPPED:        N leads  ← these need manual review
```

---

## G3 — Frontend: Leads Pool improvements

### 1. Click-through to lead card

In `apps/web/app/leads-pool/page.tsx`:
- Each table row: `onClick={() => router.push(`/leads/${lead.id}`)}`
- Cursor pointer on hover
- Do NOT break the «Взять в работу» button — it stops propagation

### 2. Search bar

Above the table, add text input:
- Placeholder: «Поиск по компании...»
- Debounce 300ms
- Sends `?q=` param to `GET /api/leads/pool`

### 3. Filter panel

Below the search bar, horizontal filter row:

```
[Сегмент ▾]  [Город ▾]  [Приоритет ▾]  [FIT ≥ _]  [Сбросить]
```

**Сегмент dropdown** — 8 options from `SEGMENT_CHOICES` + «Все»

**Город dropdown** — fetched from `GET /api/leads/cities`, autocomplete input inside dropdown

**Приоритет** — A / B / C / D / Все

**FIT ≥** — number input 0–10 (already exists as slider, keep it)

**Сбросить** — clears all filters, shown only when any filter is active

### 4. Fix city column

Currently shows "—" because `city` is empty in most leads.
After migration 0025 city will be populated from existing data.
Column should show `lead.city ?? lead.company?.city ?? "—"`
(fallback to company.city if lead.city is empty)

### 5. Segment filter in Pipeline (Воронка)

In `apps/web/app/pipeline/page.tsx` the segment filter buttons are hardcoded.
Replace with dynamic list from `SEGMENT_CHOICES`:

```typescript
// Remove hardcoded: HoReCa, Офисы, Ритейл, Производство...
// Replace with: SEGMENT_CHOICES mapped to { key, label }
import { SEGMENT_CHOICES } from '@/lib/constants/segments'
```

Create `apps/web/lib/constants/segments.ts`:
```typescript
export const SEGMENT_CHOICES = [
  { key: 'retail_food',     label: 'Продуктовый ритейл' },
  { key: 'retail_nonfood',  label: 'Непродуктовый ритейл' },
  { key: 'cafe_restaurant', label: 'Кофейни / Кафе / Рестораны' },
  { key: 'qsr',             label: 'QSR / Fast Food' },
  { key: 'petrol',          label: 'АЗС' },
  { key: 'office',          label: 'Офисы' },
  { key: 'hotel',           label: 'Отели' },
  { key: 'distributor',     label: 'Дистрибьюторы' },
] as const
```

Use this in: leads-pool filters, pipeline segment buttons, lead create/edit form segment dropdown, company card primary_segment field.

---

## Self-check

- [ ] `pnpm typecheck` — OK / NOT OK
- [ ] `pnpm build` — OK / NOT OK
- [ ] `pytest tests/ -x -q` — OK / NOT OK (baseline: 336+ passing)
- [ ] `SELECT segment, count(*) FROM leads GROUP BY segment ORDER BY count DESC` — shows only 8 known keys + any UNMAPPED — OK / NOT OK
- [ ] `SELECT count(*) FROM leads WHERE segment NOT IN ('retail_food','retail_nonfood','cafe_restaurant','qsr','petrol','office','hotel','distributor') AND segment IS NOT NULL` — should be 0 or small number — show count
- [ ] `GET /api/leads/pool` returns leads with `city` populated (not all "—") — OK / NOT OK
- [ ] `GET /api/leads/pool?segment=retail_food` returns only retail_food leads — OK / NOT OK
- [ ] `GET /api/leads/pool?q=пятерочка` returns matching leads — OK / NOT OK
- [ ] `GET /api/leads/cities` returns sorted city list — OK / NOT OK
- [ ] Clicking a leads-pool row navigates to `/leads/{id}` — OK / NOT OK
- [ ] Pipeline segment filter buttons match the 8 segments (not old hardcoded values) — OK / NOT OK

## NOT in scope

- Full segment analytics dashboard
- Bulk re-assign segment on multiple leads
- Workspace-configurable segment list (hardcoded for now)
