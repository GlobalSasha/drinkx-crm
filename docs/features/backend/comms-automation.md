# Бэкенд — Коммуникации и автоматизации

Домены: `inbox`, `email`, `notifications`, `automation`, `automation_builder`, `followups`, `template`.

Здесь живёт самая «связанная» механика: входящие сообщения, движок переходов по этапам и
пользовательские автоматизации. Порядок шагов и транзакционные границы критичны —
читай **⚠️ Подводные камни**.

---

## automation (движок переходов по этапам)

**Назначение.** Единственная точка смены `lead.stage_id` (ADR-003/011/012). Прогоняет
pre-checks (гейты), применяет переход, запускает post-actions.

**Файл.** `app/automation/stage_change.py` — `move_stage(db, lead, to_stage, user_id, gate_skipped=False, skip_reason=None)`.

**Pre-checks** (список `PRE_CHECKS`):
- `check_pipeline_match()` — **жёсткий гейт:** `to_stage.pipeline_id` должен совпадать с `lead.pipeline_id`.
- `check_economic_buyer_for_stage_6_plus()` — **мягкий гейт:** этап ≥ 6 требует контакт с `role_type=economic_buyer`.

**Post-actions** (список `POST_ACTIONS`, **порядок важен**):
1. `set_won_lost_timestamps()` — проставить `won_at/lost_at` на is_won/is_lost этапах.
2. `log_stage_change_activity()` — Activity(type=stage_change) с полным контекстом.
3. `record_stage_history()` — закрыть прошлую `LeadStageHistory` (exited_at, duration_sec), открыть новую.
4. `fan_out_automation_builder()` — диспатч stage_change-автоматизаций (через `safe_evaluate_trigger`).
5. `trigger_lead_agent_refresh()` — Celery `lead_agent_refresh_suggestion`.

**⚠️ Подводные камни.**
- **Жёсткие гейты нельзя пропустить**; мягкие — только с `skip_reason` (+ структурный лог пропуска, ADR-003).
- Нельзя двигать архивный лид (`archived_at IS NOT NULL`).
- Каждый post-action в `try/except`: падение истории/refresh логируется, но **не откатывает переход**.
  Сам переход — критичный side-effect, остальное best-effort.
- **Порядок post-actions нельзя менять:** won/lost-таймстемпы до логирования (чтобы payload был верным),
  история — после логирования, fan-out/refresh — в самом конце.

---

## automation_builder (пользовательские автоматизации)

**Назначение.** Конструктор правил: триггер → условие → действие(я), с многошаговыми цепочками и
задержками.

**Файлы** (`app/automation_builder/`):
- `models.py` — `Automation` (trigger, trigger_config_json, condition_json, action_type/config, `steps_json`, is_active), `AutomationRun` (append-only аудит), `AutomationStepRun` (по-шаговое отложенное выполнение).
- `services.py` — CRUD + `evaluate_trigger`, `safe_evaluate_trigger`, обработчики действий (`_send_template_action`, `_create_task_action`, `_move_stage_action`).
- `condition.py` — `evaluate(lead, condition_json)` → bool (деревья all/any над `ALLOWED_FIELDS`).
- `render.py` — `render_template_text(text, lead)` (подстановка `{company_name}` и т.п.).
- `dispatch.py` — пост-коммит SMTP-диспатч (Sprint 2.6): `collect_pending_email_dispatches` (ctx manager), `flush_pending_email_dispatches`.
- `repositories.py`, `routers.py`.

**Триггеры:** `stage_change` (`{to_stage_id?}`), `form_submission` (`{form_id?}`), `inbox_match` (`{}`).
**Действия:** `send_template`, `create_task`, `move_stage`.

**Эндпоинты.** `GET/POST /api/automations`, `PATCH/DELETE /api/automations/{id}`, `GET /api/automations/{id}/runs`.

**Механика выполнения.** `evaluate_trigger` вызывается из post-хуков (stage_change, после создания
лида формой, после привязки в inbox). Грузит активные автоматизации по индексу (workspace, trigger,
is_active), проверяет условия, диспатчит совпавшие. Шаг 0 — синхронно в SAVEPOINT родительской
транзакции; шаги 1+ — строки `AutomationStepRun` с будущим `scheduled_at`, которые подбирает beat-задача
`automation_step_scheduler` (каждые 5 мин). `delay_hours` сдвигает `scheduled_at` следующего шага.

**⚠️ Подводные камни.**
- **Пустое `condition_json` → срабатывает всегда.** Неизвестное поле/оператор → warning + False (не сработает).
  Старые UI-бандлы с удалёнными полями молча пропускаются.
- **Снимок шага:** `step_json` в `AutomationStepRun` заморожен на момент запуска — правка
  `Automation.steps_json` не влияет на уже летящие шаги (идемпотентность).
- **Email шлётся пост-коммитом** (Sprint 2.6): действие `send_template` стейджит Activity
  (`delivery_status=pending`), добавляет в pending-список через ContextVar; после коммита отдельная
  короткоживущая сессия шлёт письмо и обновляет `delivery_status` (sent/stub/failed), **никогда не откатывая** лид/автоматизацию.
  До 2.6 SMTP-вызов был внутри транзакции — это роняло коннект; не возвращай это.
- **Изоляция действий:** исключение в одном действии ловится и пишется в `AutomationRun.error`,
  не влияя на родительскую транзакцию и соседние автоматизации.
- **Legacy single-action** (пустой `steps_json`) трактуется как цепочка из 1 шага.

---

## inbox

**Назначение.** Входящие из Gmail, Telegram, MAX, телефонии. Матчинг входящих к лидам, хранение
несматченных, human-in-the-loop триаж email с низкой уверенностью.

**Файлы** (`app/inbox/`):
- `models.py` — `ChannelConnection` (OAuth-креды), `InboxItem` (Gmail на ревью), `InboxMessage` (мессенджеры/телефония — отдельно от email, ADR-023).
- `services.py` — `list_inbox`, `count_pending`, `confirm_item`, `dismiss_item`.
- `message_services.py` — `match_lead` (channel id → fallback phone), `receive` (вебхук → идемпотентный upsert + Activity), `send`, `list_for_lead`, `list_unmatched_messages`, `assign`.
- `message_tasks.py` — `transcribe_call_async` (STT + summary).
- `processor.py` — обработка письма: dedup Gmail, матч по confidence, маршрутизация (attach/inbox/ignore), авто-создание лида.
- `routers.py`, `gmail_client.py`, `oauth.py`, `matcher.py`, `email_parser.py`, `sync.py`, `webhooks.py`, `stt.py`.

**Эндпоинты.** `POST /api/inbox/connect-gmail`, `GET /api/inbox/gmail/callback`,
`GET /api/inbox/unmatched/messages`, `PATCH /api/inbox/messages/{id}/assign`,
`GET /leads/{id}/inbox`, `POST /leads/{id}/inbox/send`, `POST /leads/{id}/inbox/call`.

**Матчинг.** Email → по `confidence` (порог 0.8): высокий → Activity напрямую, низкий/нет → Celery
`auto_create_lead_from_email` (порог уже **0.85**). Мессенджеры/телефония → сначала channel id
(`tg_chat_id`, `max_user_id`), потом нормализованный телефон.

**⚠️ Подводные камни.**
- **Двойной dedup Gmail:** проверяются и `activities.gmail_message_id`, и `inbox_items.gmail_message_id`.
  Пропустишь любую проверку → дубликаты Activity.
- **Префиксы noreply/service** отфильтровываются до дорогих LLM-вызовов (`_NOREPLY_PREFIXES`).
- **Нормализация телефона:** ведущие 7/8 → 10-значная форма; сравнение только по нормализованному.
- **STT/summary не ре-райзят:** при сбое транскрипт = что успело, summary пустой; refresh Блейка всё равно ставится.
- `Activity.user_id` на inbox-действиях = владелец канала/подтвердивший менеджер (аудит), не scope видимости (ADR-019).

---

## email

**Назначение.** SMTP-отправитель **только** для действия `send_template` в Automation Builder.
Отдельно от notifications-сендера ради stub-семантики.

**Файл.** `app/email/sender.py` — `send_email(to, subject, body, settings?)` → `bool` | `EmailSendError`.

**⚠️ Подводные камни.**
- **Возвращаемое значение — семантика, не ошибка:** `False` = stub-режим (нет SMTP_HOST, нет сетевого I/O),
  `True` = отправлено, `EmailSendError` = сбой SMTP. Никогда не трактуй `False` как ошибку.
- Только plain-text, без HTML-multipart.

---

## notifications

**Назначение.** Системные уведомления с дедуп-окном (1 ч на kind+user) и подавлением пустого плана.

**Файлы** (`app/notifications/`): `models.py` (`Notification`), `schemas.py`,
`services.py` (`notify`, `safe_notify`, `list_for_user`, `mark_read`, `mark_all_read`, `dismiss`), `routers.py`.

**Виды (`kind`).** `lead_transferred`, `enrichment_done`, `enrichment_failed`, `daily_plan_ready`,
`followup_due`, `mention`, `system`, `invite_accepted`.

**Эндпоинты.** `GET /notifications`, `POST /{id}/read`, `POST /mark-all-read`, `DELETE /{id}`.

**⚠️ Подводные камни.**
- **Правила подавления:** (1) пустой `daily_plan_ready` (body начинается с `0 карточек`) → skip;
  (2) тот же `(workspace, user, kind)` в пределах 1 ч → skip, кроме `DEDUP_EXEMPT_KINDS` (сейчас только `lead.urgent_signal`).
- **Формат пустого плана** проверяется по точной строке `"{N} карточек, ~{мин} мин"` — любая вариация обходит подавление.
- `notify()` делает flush, **не commit** — коммитит вызывающий. `safe_notify()` глотает исключения (для cron/оркестратора).
- `read` оставляет строку, `dismiss` — жёстко удаляет.

---

## followups

**Назначение.** Lead-scoped задачи/напоминания с дефолтным чек-листом и cron-диспетчером
(за 24 ч до срока).

**Файлы** (`app/followups/`): `models.py` (`Followup`), `services.py` (CRUD + `seed_for_lead`,
`get_pending_counts_for_user`), `repositories.py` (`count_pending_for_user` через `COUNT(*) FILTER`),
`dispatcher.py` (`run_followup_dispatch`), `routers.py`.

**Модель `Followup`** — `lead_id` (CASCADE), `name`, `due_at`, `status` (pending/active/done/overdue),
`reminder_kind` (manager/auto_email/ai_hint), `position`, `completed_at`, `dispatched_at`.

**Эндпоинты.** `GET/POST /leads/{lead_id}/followups`, `PATCH/DELETE /{fu_id}`, `POST /{fu_id}/done`,
`GET /me/followups-pending` (виджет Today).

**Диспетчер (`run_followup_dispatch`, cron 15 мин).** Берёт `dispatched_at IS NULL AND due_at <= now+24h
AND status IN (pending, active)`. Для каждого: Activity(type=reminder) + `dispatched_at=now` (идемпотентность)
+ `safe_notify(kind=followup_due)` назначенному менеджеру.

**⚠️ Подводные камни.**
- **Идемпотентность через `dispatched_at`:** повторный прогон cron в том же окне — no-op.
- На создании лида автоматически зовётся `seed_for_lead` (3 дефолтных пункта).
- Если лид удалён между созданием и диспатчем — Activity всё равно создаётся, уведомление пропускается (`assigned_to` = None).

---

## template

**Назначение.** Библиотека шаблонов сообщений для Automation Builder. Workspace-scoped,
канало-специфичные (email/tg/sms).

**Файлы** (`app/template/`): `models.py` (`MessageTemplate`, unique `(workspace_id, name, channel)`),
`schemas.py`, `services.py`, `repositories.py`, `routers.py`.

**Эндпоинты.** `GET /api/templates?channel=`, `POST` (admin), `PATCH /{id}` (admin), `DELETE /{id}` (admin).

**⚠️ Подводные камни.**
- **Гард «в использовании» (Sprint 2.6):** `delete_template` сканирует активные автоматизации с
  `action_type=send_template` и `action_config_json["template_id"] == id`. Найдено → `TemplateInUse` (409).
  Не убирай этот гард — иначе удаление молча сломает автоматизации.
- Дедуп `(workspace, name, channel)` ловит и переименования (409).
- `category` обнуляется только явным `{"category": null}` в PATCH.
- Текст шаблона не валидируется на переменные — `{unknown_field}` отрендерится как есть.
- Только hard-delete; soft-disable нет.
