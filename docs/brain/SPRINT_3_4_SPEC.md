# Sprint 3.4 — Team Dashboard + Manager Removal

## Context

Three goals:
1. New `/team` page — activity dashboard for each manager (admin/head only)
2. Delete manager button in Settings → Команда (admin only)
3. Fix «Команда» sidebar nav link → points to `/settings?section=team`

No new migrations needed — all data already exists in `activities`, `audit_log`, `leads`, `users`.

---

## G1 — Backend: Team Stats API

### New endpoint `GET /api/team/stats`

Query params:
- `period`: `today` | `week` | `month` (default: `week`)

Auth: admin or head role only (403 otherwise).

Response:
```json
{
  "period": "week",
  "from": "2026-05-05T00:00:00Z",
  "to": "2026-05-11T23:59:59Z",
  "managers": [
    {
      "user_id": "uuid",
      "name": "Кирилл Перов",
      "email": "k.perov@drinkx.tech",
      "avatar_url": null,
      "role": "manager",
      "stats": {
        "kp_sent": 3,
        "leads_taken_from_pool": 5,
        "leads_moved": 12,
        "tasks_completed": 8
      },
      "last_active_at": "2026-05-11T14:32:00Z"
    }
  ]
}
```

### SQL logic per metric

**kp_sent** — activities where user created a file activity with file_kind = 'kp':
```sql
SELECT count(*) FROM activities
WHERE user_id = :uid
  AND type = 'file'
  AND file_kind = 'kp'
  AND created_at >= :from AND created_at <= :to
```

**leads_taken_from_pool** — leads assigned to this user during the period:
```sql
SELECT count(*) FROM leads
WHERE assigned_user_id = :uid
  AND assignment_status = 'assigned'
  AND updated_at >= :from AND updated_at <= :to
```

Note: this is an approximation — updated_at changes on any update. If precision matters later,
a lead_assignments log table should be added (Phase 2). For v1 this is acceptable.

**leads_moved** — audit_log entries for stage moves by this user:
```sql
SELECT count(*) FROM audit_log
WHERE user_id = :uid
  AND action = 'lead.move_stage'
  AND created_at >= :from AND created_at <= :to
```

**tasks_completed** — activities where this user completed a task:
```sql
SELECT count(*) FROM activities
WHERE user_id = :uid
  AND type = 'task'
  AND task_done = true
  AND task_completed_at >= :from AND task_completed_at <= :to
```

### New endpoint `GET /api/team/stats/{user_id}`

Returns daily breakdown for one manager.
Same period query param.

Response adds `daily` array:
```json
{
  "user_id": "uuid",
  "name": "Кирилл Перов",
  "period": "week",
  "stats": { "kp_sent": 3, "leads_taken_from_pool": 5, "leads_moved": 12, "tasks_completed": 8 },
  "daily": [
    { "date": "2026-05-05", "kp_sent": 0, "leads_taken_from_pool": 2, "leads_moved": 3, "tasks_completed": 1 },
    { "date": "2026-05-06", "kp_sent": 1, "leads_taken_from_pool": 1, "leads_moved": 2, "tasks_completed": 2 }
  ]
}
```

### Package structure

```
app/team/
  __init__.py
  schemas.py
  repositories.py   — raw SQL aggregations
  services.py       — period calculation + call repositories
  routers.py        — GET /api/team/stats, GET /api/team/stats/{user_id}
```

Register router in `app/main.py` under prefix `/api/team`.

---

## G2 — Backend: Delete Manager

### New endpoint `DELETE /api/users/{user_id}`

Auth: admin only (403 otherwise).

Rules:
- Cannot delete yourself → 400 `{ "code": "cannot_delete_self" }`
- Cannot delete last admin → 400 `{ "code": "last_admin" }` (same guard as role demotion)
- On delete:
  1. Reassign all active leads (`assigned_user_id = user_id AND archived_at IS NULL`) back to pool: `SET assigned_user_id = NULL, assignment_status = 'pool'`
  2. `DELETE FROM users WHERE id = :user_id`
  3. Write audit_log: `action="user.delete"`, `entity_type="user"`, `entity_id=user_id`, `delta={email, name, role}`

Response: `204 No Content` on success.

Note: activities, audit_log rows created by this user are kept (historical record).
leads are returned to pool so other managers can pick them up.

---

## G3 — Frontend: `/team` page

### Route: `apps/web/app/team/page.tsx`

Access: admin and head roles only. Redirect to `/today` for managers.

### Layout

Header:
- Title: «Команда»
- Period switcher: «Сегодня» | «Неделя» | «Месяц» (default: Неделя)
- Shows date range: «5–11 мая»

Manager cards (grid, 2 columns on desktop, 1 on mobile):

```
┌─────────────────────────────────────┐
│ 👤 Кирилл Перов          manager    │
│    k.perov@drinkx.tech              │
│    последняя активность: 2 ч назад  │
│                                     │
│  КП        Из пула   Продвинуто  Задачи │
│   3          5          12          8   │
└─────────────────────────────────────┘
```

Click on card → navigate to `/team/[user_id]`

### Route: `apps/web/app/team/[user_id]/page.tsx`

Shows:
- Manager name + role + email
- Same period switcher
- Total stats (same 4 metrics)
- Daily breakdown table:

| Дата | КП | Из пула | Продвинуто | Задачи |
|---|---|---|---|---|
| Пн 5 мая | 0 | 2 | 3 | 1 |
| Вт 6 мая | 1 | 1 | 2 | 2 |

Back button → `/team`

### Hooks

- `lib/hooks/use-team-stats.ts` — `useTeamStats(period)` → calls `GET /api/team/stats`
- `lib/hooks/use-manager-stats.ts` — `useManagerStats(userId, period)` → calls `GET /api/team/stats/{user_id}`

---

## G4 — Frontend: Delete manager + nav fix

### Delete manager button

Location: `components/settings/TeamSection.tsx` (already exists from Sprint 2.4)

Add delete button (🗑) per manager row, visible to admin only.

Flow:
1. Click 🗑 → confirmation modal: «Удалить {name}? Все его лиды вернутся в пул.»
2. Confirm → `DELETE /api/users/{user_id}`
3. On 400 `cannot_delete_self` → toast: «Нельзя удалить себя»
4. On 400 `last_admin` → toast: «Нельзя удалить последнего администратора»
5. On 204 → remove from list, show toast: «Менеджер удалён, лиды возвращены в пул»

### Fix «Команда» nav link

File: `apps/web/components/layout/AppShell.tsx` (or wherever sidebar nav is defined)

Find the «Команда» nav item. Change `href` to `/settings?section=team` or wherever
the TeamSection is reachable. If the nav item currently has no `href` or `onClick` — add it.

Also check: «База знаний» nav item. If it has no route → add `href="/knowledge"` but render
page as «Скоро» stub (empty state with «Раздел в разработке» message).
Do NOT build the Knowledge Base in this sprint — stub only.

---

## Self-check

After implementation, run each item and write OK or NOT OK:

- [ ] `pnpm typecheck` — OK / NOT OK
- [ ] `pytest tests/ -x -q` — OK / NOT OK (show count, baseline is 336 passing)
- [ ] `GET /api/team/stats?period=week` returns managers array with 4 stats each — OK / NOT OK
- [ ] `GET /api/team/stats?period=today` returns same structure — OK / NOT OK
- [ ] `GET /api/team/stats/{user_id}?period=week` returns daily breakdown — OK / NOT OK
- [ ] `DELETE /api/users/{self_id}` returns 400 `cannot_delete_self` — OK / NOT OK
- [ ] `DELETE /api/users/{last_admin_id}` returns 400 `last_admin` — OK / NOT OK
- [ ] After DELETE: deleted user's leads have `assignment_status = 'pool'` — OK / NOT OK
- [ ] `/team` page renders for admin, redirects to `/today` for manager role — OK / NOT OK
- [ ] «Команда» nav link is clickable and navigates correctly — OK / NOT OK
- [ ] «База знаний» nav link is clickable and shows stub page — OK / NOT OK

## NOT in scope

- Knowledge Base actual implementation — separate sprint
- Manager performance charts / graphs — v2
- Export team stats to CSV — v2
- Activity feed per manager (who touched which lead) — v2
