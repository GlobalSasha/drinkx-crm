# Sprint 2.6 — Post-deploy smoke checklist

Supplement to `SMOKE_CHECKLIST_2_4.md` + `SMOKE_CHECKLIST_2_5.md`,
NOT a replacement. Run prior checklists first; then the 8 new 2.6
checks below. Both lists should run on staging immediately after
the sprint branch lands and again on prod after merge to main.

Same rule as before: every row needs an actual visit in a logged-in
browser tab — DevTools Network tab open, "Preserve log" enabled,
zero non-2xx tolerated.

## Setup

- Workspace seeded with: at least 1 user, 1 pipeline, 1 lead with a
  valid email, 1 message template (channel='email'), 1 active
  automation (trigger=stage_change, action=send_template, template
  pointing at the template above), at least 2 custom-attribute
  definitions of mixed kinds (text + select).
- Sub-375px viewport handy (DevTools mobile preview is fine) for
  the mobile-pipeline check.
- Two browser sessions: admin + non-admin (manager role) for the
  permission-gated checks.

## New 2.6 checks

| # | Page / Flow | Verify |
|---|---|---|
| 1 | `/leads/{id}` → LeadCard right rail | New «Кастомные поля» panel renders below the FollowupsRail. Each definition shows a row with label on the left, value (or «не заполнено» italic) on the right. The panel renders nothing if the workspace has no definitions — that's expected, not a bug. |
| 2 | LeadCard custom field — text inline edit | Click on the value cell of a text-kind field → it becomes an `<input type="text">` with cursor at end. Type a new value, press Enter → request fires, value persists. Reload the page → value still there. Press Escape mid-edit → original value restored. |
| 3 | LeadCard custom field — select inline edit | Click on a select-kind field → `<select>` dropdown appears. Pick an option → request fires immediately on change (no Enter needed). Value displays as the option's `label`, not the raw `value`. Empty selection clears the value. |
| 4 | LeadCard custom field — empty state | A field with no value renders «не заполнено» in muted italic gray. After saving any value the placeholder disappears. After clearing the value (text → empty + Enter) the placeholder returns. |
| 5 | Settings → Кастомные поля → drag reorder | Each row shows a `≡` grip handle on the left (admin/head only). Drag a row up or down — the order changes immediately. Reload the page — the new order persists. Network tab shows `PATCH /api/custom-attributes/reorder` 200 with the new `ordered_ids` body. Manager-role users see no grip handle and cannot reorder. |
| 6 | Settings → Шаблоны → delete in-use template | Create an automation that references template T. Try to delete T from `/settings → Шаблоны`. The delete request returns 409; the UI surfaces the structured error («Шаблон используется активной автоматизацией»). The template is NOT deleted. Disable the automation (`is_active=false`); retry the delete — succeeds. |
| 7 | `/pipeline` header — primary button styling | The «+Лид» button has `bg-accent` (purple fill, white text). The «Сформировать план на неделю» button has the outline style (transparent bg, accent border, accent text). Visual hierarchy: +Лид is the loud daily CTA, Sprint is the secondary periodic action. |
| 8 | `/pipeline` on mobile (<768px viewport) | Resize the viewport below 768px. The Kanban columns disappear; a single-column vertical list of leads renders, grouped under stage section headings. Each card shows: company name, stage badge (color dot + name), segment / city, priority chip. No horizontal overflow. Drag-and-drop is disabled (touch interaction was out of scope per Sprint 1.5 PRD §8.6). Tap a card → navigates to `/leads/{id}`. |

## If anything fails

- **Don't merge** (or roll back the merge if already on prod).
- Capture the failing request payload + response in
  `SPRINT_2_6_OUTBOUND_EMAIL.md`'s production-readiness section.
- Hotfix pattern: `hotfix/{slug}` branch off main, fix + test, PR
  back. See `hotfix/single-workspace`, `hotfix/celery-mapper-registry`
  for the established shape.

## Operator notes

### `send_template` dispatch state

Sprint 2.6 G1 + stability fix flipped `send_template` from a stub
Activity to actual SMTP delivery via `app/email/sender.py`. The
post-commit drainer in `app/automation_builder/dispatch.py` opens a
**new short-lived session** to update the Activity row's
`delivery_status` after SMTP returns. Behaviour matrix:

| `SMTP_HOST` env | `lead.email` | Outcome |
|---|---|---|
| empty (stub mode) | any | Activity → `delivery_status='stub'`. No network I/O. Worker log: `[EMAIL STUB outbound]`. |
| set | None or whitespace | Activity → `delivery_status='skipped_no_email'`. Worker log: `automation.send_template.skipped_no_email`. No SMTP attempt. |
| set | valid | Activity → `delivery_status='sent'` after aiosmtplib succeeds. |
| set | valid + SMTP rejects | Activity → `delivery_status='failed'` + `delivery_error` payload field. Drainer logs `automation.dispatch.send_failed`. Does NOT re-raise — the parent transaction (Activity row + automation_runs row) already committed. |

Surface this matrix to admins during the Sprint 2.6 announcement so
they don't expect an email to arrive when staging is in stub mode.

### tg / sms channels still stubbed

Templates with `channel='tg'` or `channel='sms'` keep the Sprint 2.5
«pending» state — Activity row stages with
`delivery_status='pending'` + `outbound_pending=true`. Real
providers land in Sprint 2.7+ when the bot library + SMS vendor are
picked. Admins should know: configuring a tg-channel automation
today produces an audit trail in the lead's Activity Feed but no
actual message goes out.

### Custom field rendering on existing leads

Sprint 2.4 G3 shipped the schema (migration 0018); Sprint 2.6 G4
shipped the UI. Existing leads in production now show the panel as
soon as the workspace has at least one `custom_attribute_definition`.
The list of fields comes from `GET /api/custom-attributes` (already
deployed since 2.4 G3); no data backfill needed.

### Reorder is admin/head only

The drag handle in `/settings → Кастомные поля` is gated by
`require_admin_or_head` on the backend (`PATCH
/api/custom-attributes/reorder`) and hidden in the UI for managers.
A manager who somehow PATCHes the endpoint directly gets 403; the
UI never offers the affordance.
