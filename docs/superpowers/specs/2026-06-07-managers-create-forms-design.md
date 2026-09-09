# Managers can create & edit web forms

**Date:** 2026-06-07
**Type:** Permissions change (no new functionality)

## Problem

The WebForms feature (create, edit, embed code, analytics) is fully built but
gated to `admin`/`head` roles. Plain `manager` users are redirected off
`/forms` entirely. We want managers to create and manage forms so they don't
have to ask an admin for every landing-page form.

## Decision

Managers get **full create + edit**, including the `is_active` toggle and the
`require_key` setting. Only two genuinely destructive operations stay
admin/head-only:

- **Delete** a form (the `DELETE` endpoint).
- **Rotate the ingest key** (invalidates existing S2S integrations).

Managers act on **all workspace forms** — no per-row ownership checks.

### Permission matrix (after)

| Action | admin/head | manager |
|---|---|---|
| View forms / submissions / stats | ✅ | ✅ |
| See `ingest_token` + embed snippet | ✅ | ✅ |
| Create form | ✅ | ✅ |
| Edit config (name, fields, target, redirect, assignee, SLA, autoreply) | ✅ | ✅ |
| Toggle `is_active` | ✅ | ✅ |
| Toggle `require_key` | ✅ | ✅ |
| Delete form | ✅ | ❌ |
| Rotate ingest key | ✅ | ❌ |

## Changes

### Backend — `apps/api/app/forms/routers.py`
1. `create_form`: `require_admin_or_head` → `current_user`.
2. `update_form`: `require_admin_or_head` → `current_user`.
3. `get_stats`: `require_admin_or_head` → `current_user` (already
   workspace-guarded) so the per-row stats card loads for managers.
4. `list_forms` + `get_form`: always include `ingest_token` in the response
   (drop the admin/head-only stripping) since every authed role can now
   manage forms.

`delete_form` and `rotate_form_key` keep `require_admin_or_head`.

No DB migration, no schema change, no new endpoints.

### Frontend
- `apps/web/app/(app)/forms/page.tsx`: remove the manager→`/today` redirect and
  the forbidden-content guard; allow all authed roles onto the page. Hide the
  per-row **delete (trash)** button for non-admin/head users (active toggle
  stays for everyone).
- `apps/web/components/forms/FormEditor.tsx`: hide the **"Перевыпустить ключ"**
  (rotate-key) button for non-admin/head users. The embed code + token stay
  visible.

## Out of scope
Per-row ownership, new roles, audit logging changes.
