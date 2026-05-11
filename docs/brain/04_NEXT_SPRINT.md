# Sprint 3.3 — Companies + Global Search

## Context

`company_name` is currently a plain text field on `leads`. This sprint makes `companies` a
full account-layer above leads — the standard B2B CRM model.

**ADR-022** (record in `docs/brain/03_DECISIONS.md`):

```
Company = Account  (stable identity: name, INN, domain, contacts)
Lead    = Deal/Opportunity  (working state: stage, segment, score, owner)

company_name on leads  → snapshot/cache, NOT source of truth
contacts.lead_id       → legacy/context for v1
lead_contacts junction table → backlog Phase 2
company_aliases              → backlog Phase 2
```

---

## G1 — Schema (Alembic migration)

### New table `companies`

```sql
CREATE TABLE companies (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name            VARCHAR(255) NOT NULL,
  normalized_name VARCHAR(255) NOT NULL,
  legal_name      VARCHAR(255),
  inn             VARCHAR(12),
  kpp             VARCHAR(9),
  domain          VARCHAR(255),
  website         VARCHAR(255),
  phone           VARCHAR(50),
  email           VARCHAR(255),
  city            VARCHAR(100),
  address         TEXT,
  primary_segment VARCHAR(50),
  employee_range  VARCHAR(30),
  notes           TEXT,
  is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
  archived_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Alter existing tables

```sql
-- leads
ALTER TABLE leads ADD COLUMN company_id UUID REFERENCES companies(id) ON DELETE SET NULL;

-- contacts: nullable first, NOT NULL set AFTER backfill in separate migration
ALTER TABLE contacts ADD COLUMN workspace_id UUID REFERENCES workspaces(id);
ALTER TABLE contacts ADD COLUMN company_id   UUID REFERENCES companies(id) ON DELETE SET NULL;
```

### Indexes

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- companies
CREATE UNIQUE INDEX uq_companies_inn
  ON companies(workspace_id, inn)
  WHERE inn IS NOT NULL AND is_archived = false;

CREATE INDEX idx_companies_workspace   ON companies(workspace_id);
CREATE INDEX idx_companies_name_trgm   ON companies USING gin(name gin_trgm_ops);
CREATE INDEX idx_companies_normalized  ON companies(workspace_id, normalized_name);
CREATE INDEX idx_companies_domain      ON companies(workspace_id, domain) WHERE domain IS NOT NULL;

-- leads
CREATE INDEX idx_leads_company_id      ON leads(company_id);
CREATE INDEX idx_leads_name_trgm       ON leads USING gin(company_name gin_trgm_ops);

-- contacts
CREATE INDEX idx_contacts_company_id   ON contacts(company_id);
CREATE INDEX idx_contacts_workspace    ON contacts(workspace_id);
CREATE INDEX idx_contacts_name_trgm    ON contacts USING gin(name gin_trgm_ops);
CREATE INDEX idx_contacts_email        ON contacts(workspace_id, email) WHERE email IS NOT NULL;
CREATE INDEX idx_contacts_phone        ON contacts(workspace_id, phone) WHERE phone IS NOT NULL;
```

---

## G2 — Backend helpers (`app/companies/utils.py`)

```python
import re

_ORG_FORMS = re.compile(
    r'\b(ооо|пао|ао|зао|ип|нао|мсп|llc|ltd|inc|gmbh|s\.a)\b',
    flags=re.IGNORECASE | re.UNICODE
)

def normalize_company_name(name: str) -> str:
    s = name.lower().strip()
    s = s.replace('«', '').replace('»', '').replace('"', '').replace("'", '')
    s = _ORG_FORMS.sub('', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url if '://' in url else 'https://' + url)
        host = parsed.hostname or ''
        return host.removeprefix('www.').lower() or None
    except Exception:
        return None
```

These helpers are called in `services.py` only. Never accept `normalized_name` or `domain`
from the frontend.

---

## G3 — Backend domain (`app/companies/`)

Package structure (ADR-009 package-per-domain):
```
app/companies/
  __init__.py
  models.py
  schemas.py
  repositories.py
  services.py
  routers.py
  merge.py
```

### Creation logic — 409 Conflict protection

**`services.py`:**

```python
from sqlalchemy import func
from app.leads.models import Lead

def create_company(db, workspace_id, data, force=False):
    normalized = normalize_company_name(data.name)

    if not force:
        candidates = db.query(
            Company,
            func.count(Lead.id).label('leads_count')
        ).outerjoin(
            Lead, Lead.company_id == Company.id
        ).filter(
            Company.workspace_id == workspace_id,
            Company.normalized_name == normalized,
            Company.is_archived == False
        ).group_by(Company.id).all()

        if candidates:
            raise DuplicateCompanyWarning(candidates=candidates)

    company = Company(
        workspace_id=workspace_id,
        name=data.name,
        normalized_name=normalized,
        domain=extract_domain(data.website),
        # ... other fields from data
    )
    db.add(company)
    db.commit()
    return company
```

**`routers.py`:**

```python
@router.post("/", status_code=201)
def create(payload: CompanyIn, force: bool = False, ...):
    try:
        return companies_service.create_company(db, workspace_id, payload, force=force)
    except DuplicateCompanyWarning as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_warning",
                "candidates": [
                    {
                        "id": str(c.Company.id),
                        "name": c.Company.name,
                        "inn": c.Company.inn,
                        "leads_count": c.leads_count
                    }
                    for c in e.candidates
                ]
            }
        )
```

### Sync rule for `company_name`

- On `PATCH /companies/{id}` name change → `UPDATE leads SET company_name = :new_name WHERE company_id = :id AND is_archived = false`
- On lead creation with `company_id` → copy `company.name` into `leads.company_name`
- Direct edit of `leads.company_name` via API is only allowed when `company_id IS NULL`

---

## G4 — API endpoints

```
GET    /api/companies                          list (filters: city, primary_segment, is_archived)
GET    /api/companies/{id}                     card: data + leads + contacts + last 20 activities
POST   /api/companies                          create (with duplicate_warning / force logic)
PATCH  /api/companies/{id}                     update
DELETE /api/companies/{id}                     soft archive
POST   /api/companies/{source_id}/merge-into/{target_id}
```

### Merge logic (`merge.py`)

1. If both `source.inn` and `target.inn` are set and differ → `409 { "code": "inn_conflict" }` (requires `?force=true`)
2. If `target.inn IS NULL` and `source.inn IS NOT NULL` → transfer INN to target
3. Move leads — protect historical records:

```sql
UPDATE leads l
SET company_id   = :target_id,
    company_name = CASE
        WHEN l.is_archived = false
         AND NOT EXISTS (
             SELECT 1 FROM stages s
             WHERE s.id = l.stage_id
               AND (s.is_won = true OR s.is_lost = true)
         )
        THEN :target_name
        ELSE l.company_name
    END
WHERE l.company_id = :source_id;
```

4. `UPDATE contacts SET company_id = :target_id WHERE company_id = :source_id`
5. `source.is_archived = true`, `source.archived_at = now()`
6. Write `company.merge` to audit_log with payload `{source_id, target_id}`

---

## G5 — Global Search (`app/search/`)

**Endpoint:** `GET /api/search?q=текст&limit=20`

Fork query by length in `app/search/repositories.py`:

```python
def search(db, workspace_id, q, limit=20):
    q = q.strip()
    if len(q) < 3:
        return _search_ilike(db, workspace_id, q, limit)
    else:
        return _search_trgm(db, workspace_id, q, limit)
```

- `_search_ilike` — `ILIKE '%q%'` only, exact match on INN/email/phone. No `similarity()`, no `%` trigram operator.
- `_search_trgm` — full CTE with `similarity()` and ranked UNION:

```sql
WITH query AS (
  SELECT :wid::uuid AS workspace_id, trim(:q) AS q, '%' || trim(:q) || '%' AS q_like
)
SELECT * FROM (

  SELECT 'company' AS type, c.id, c.name AS title,
    COALESCE('ИНН: ' || c.inn, c.city, '') AS subtitle,
    NULL::uuid AS lead_id,
    '/companies/' || c.id AS url,
    GREATEST(similarity(c.name, q.q), similarity(COALESCE(c.inn,''), q.q)) AS rank
  FROM companies c, query q
  WHERE c.workspace_id = q.workspace_id AND c.is_archived = false
    AND (c.name % q.q OR c.inn ILIKE q.q_like OR c.website ILIKE q.q_like)

  UNION ALL

  SELECT 'lead' AS type, l.id, l.company_name AS title,
    s.name AS subtitle, l.id AS lead_id,
    '/leads/' || l.id AS url,
    similarity(l.company_name, q.q) AS rank
  FROM leads l
  LEFT JOIN stages s ON s.id = l.stage_id, query q
  WHERE l.workspace_id = q.workspace_id
    AND (l.company_name % q.q OR l.email ILIKE q.q_like OR l.phone ILIKE q.q_like)

  UNION ALL

  SELECT 'contact' AS type, ct.id, ct.name AS title,
    COALESCE(ct.email, ct.phone, '') AS subtitle,
    ct.lead_id,
    CASE
      WHEN ct.lead_id IS NOT NULL    THEN '/leads/' || ct.lead_id
      WHEN ct.company_id IS NOT NULL THEN '/companies/' || ct.company_id
      ELSE '/contacts/' || ct.id
    END AS url,
    GREATEST(
      similarity(ct.name, q.q),
      similarity(COALESCE(ct.email,''), q.q),
      similarity(COALESCE(ct.phone,''), q.q)
    ) AS rank
  FROM contacts ct, query q
  WHERE ct.workspace_id = q.workspace_id
    AND (ct.name % q.q OR ct.email ILIKE q.q_like OR ct.phone ILIKE q.q_like)

) results
ORDER BY rank DESC
LIMIT :limit;
```

---

## G6 — Backfill script (`scripts/backfill_companies.py`)

Run manually after G1 migration. NOT part of Alembic. Deduplicate by `normalized_name`, not raw `company_name`.

```python
from app.companies.utils import normalize_company_name, extract_domain

rows = db.execute("""
    SELECT workspace_id, company_name, segment, website, city
    FROM leads
    WHERE company_name IS NOT NULL AND company_name != ''
""")

seen = {}  # (workspace_id, normalized_name) -> company_id

for row in rows:
    key = (row.workspace_id, normalize_company_name(row.company_name))
    if key not in seen:
        company = insert_company(
            workspace_id=row.workspace_id,
            name=row.company_name,          # keep original casing from first occurrence
            normalized_name=key[1],
            domain=extract_domain(row.website),
            primary_segment=row.segment,
            city=row.city
        )
        seen[key] = company.id

# Step 2: link leads
db.execute("""
    UPDATE leads l SET company_id = mapping.company_id
    FROM (VALUES ...) AS mapping(company_name, workspace_id, company_id)
    WHERE l.company_name = mapping.company_name
      AND l.workspace_id = mapping.workspace_id
""")

# Step 3: backfill contacts.workspace_id
db.execute("""
    UPDATE contacts ct
    SET workspace_id = l.workspace_id
    FROM leads l
    WHERE ct.lead_id = l.id AND ct.workspace_id IS NULL
""")

# Step 4: backfill contacts.company_id
db.execute("""
    UPDATE contacts ct
    SET company_id = l.company_id
    FROM leads l
    WHERE ct.lead_id = l.id AND l.company_id IS NOT NULL
""")

# Step 5: print report
print("Companies created:", ...)
print("Leads linked:", ...)
print("Contacts linked:", ...)
print("Merge candidates (same normalized_name, different id):", ...)

# Acceptance check
assert db.execute("SELECT count(*) FROM contacts WHERE workspace_id IS NULL").scalar() == 0
```

After successful backfill, run separate Alembic migration:
```sql
ALTER TABLE contacts ALTER COLUMN workspace_id SET NOT NULL;
```

---

## G7 — Frontend

### Global Search — `Cmd+K`

- `components/search/GlobalSearch.tsx` — overlay, debounce 200ms
- Hotkey: `Cmd+K` / `Ctrl+K`
- Group results by type: Компании / Лиды / Контакты
- Click → navigate to `url` from API response

### Company Card — `/companies/[id]`

- Inline-editable company data
- Associated leads (table: stage, amount, manager)
- Associated contacts
- Last 20 activities aggregated from associated leads (no new table — query via leads)
- Button: «Создать лид по этой компании»
- Button: «Объединить дубль» (admin only) — search for merge target

### Lead creation — company autocomplete

- Replace text input with autocomplete field
- Search via `GET /api/search?q=&limit=10` (type=company only)
- Last item: «Создать новую: {text}»
- On select → `company_id` in payload, `company_name` filled automatically from company

### Duplicate warning modal flow

```
POST /api/companies  (no force flag)
        ↓
  201 → done
        ↓
  409 duplicate_warning →
      show modal: «Похожая компания: {name} ({leads_count} сделки).
                   Использовать или создать новую?»
            ↓                            ↓
  «Использовать»               «Создать новую»
  use candidates[0].id         POST /api/companies?force=true → 201
  DB untouched
```

### What NOT to build in this sprint

- Company-level AI Brief
- Company-level tasks / activities (separate table)
- `/companies` list page — only card via direct link or Cmd+K result

---

## Acceptance criteria

- [ ] `SELECT * FROM companies LIMIT 10` returns readable records without frontend
- [ ] `SELECT count(*) FROM contacts WHERE workspace_id IS NULL` = 0 after backfill
- [ ] `SELECT count(*) FROM leads WHERE company_name IS NOT NULL AND company_id IS NULL` = 0 after backfill
- [ ] `GET /api/search?q=` returns companies + leads + contacts with correct rank order
- [ ] Search by INN returns exact match
- [ ] Search with 2-character query does not crash and does not return noise
- [ ] `POST /api/companies` with duplicate normalized_name returns 409 (not 500)
- [ ] `POST /api/companies?force=true` creates company despite duplicate warning
- [ ] Merge with different INNs returns 409 `inn_conflict` without `?force=true`
- [ ] After merge: all source leads have `company_id = target_id`
- [ ] After merge: closed/won/lost leads keep original `company_name` snapshot
- [ ] `pnpm typecheck` clean, all existing tests green

---

## NOT in scope (backlog)

- `company_aliases` table — Phase 2
- `lead_contacts` junction table — Phase 2
- `/companies` list page — next sprint after card is live
- Company-level AI Brief — Phase 2
