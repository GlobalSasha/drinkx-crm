# Заявки с сайтов → CRM: входящие лиды с маршрутизацией и задачами

**Дата:** 2026-06-02
**Статус:** design (ожидает ревью)
**Домены:** `forms`, `leads`, `activity`, `notifications`

## 1. Проблема

У DrinkX 3–4 сайта (1 основной + 2–3 лендинга), все — собственной разработки,
у каждого своя форма «оставить заявку» и свой бэкенд (он же шлёт письмо отделу).
Нужно, чтобы заявка с любого сайта:

1. падала в CRM как входящий лид в общую базу лидов;
2. была промаркирована источником (каким сайтом) — для аналитики по каналам;
3. сразу назначалась ответственному менеджеру **по источнику** (разные сайты →
   разные менеджеры);
4. сразу превращалась в задачу «Связаться» с дедлайном (SLA);
5. принималась по **надёжному server-to-server контракту с секретным ключом**
   (сайты свои, у каждого есть бэкенд).

Отправка письма на почту отдела остаётся **на стороне сайтов** — вне зоны CRM.

## 2. Что уже есть (домен `forms`, спринт 2.2+)

Поток «заявка → лид в пул» построен и работает:

- `POST /api/public/forms/{slug}/submit` — публичный приём JSON, маппинг полей
  RU/EN (`app/forms/lead_factory.py`);
- лид создаётся с `source="form:{slug}"`, пишется `source_domain` (Referer) и UTM;
- каждая заявка сохраняется в `FormSubmission` (сырой payload + атрибуция + IP);
- в ленту лида пишутся `Activity(type=form_submission)` и комментарий;
- админам летит in-app уведомление «Новая заявка с формы»;
- админка `/forms` (создание форм, статистика, embed-сниппет), rate-limit по IP,
  CORS только для `/api/public/*`, триггер `form_submission` в Automation Builder.

**Чего нет:** маршрутизации на менеджера, авто-задачи, аутентификации по ключу,
сводной аналитики по каналам. Текущее поведение по ADR-007 — лид всегда в пул,
менеджер забирает вручную.

## 3. Решение (выбранные варианты)

- **Контракт:** server-to-server с заголовком `X-Form-Key`. Реализуется как
  опциональный `ingest_token` на форме: если задан — submit требует совпадения
  ключа, иначе 401. Если не задан — старое открытое поведение (обратная
  совместимость, годится для статичных лендингов). Один эндпоинт, уровень защиты
  выбирается на форме.
- **Маршрутизация:** фиксированный владелец на форму (`default_assignee_id`).
  Задан → лид сразу `assigned` на него + задача «Связаться». Не задан → пул
  (как сейчас).
- **SLA задачи:** поле `contact_task_sla_hours` на форме, дефолт **2**.

> **Ревизия ADR-007.** Раньше форма принципиально не назначала менеджера. Теперь —
> назначает, **если на форме явно задан владелец**. Это осознанное продуктовое
> изменение; дефолт (без владельца) сохраняет прежнее поведение.

## 4. Архитектура

### 4.1. Модель данных — миграция `0041`

Новые колонки в `web_forms`:

| Колонка | Тип | Назначение |
|---|---|---|
| `ingest_token` | `String(64)` nullable | секрет S2S; если NOT NULL — submit требует `X-Form-Key` |
| `default_assignee_id` | `UUID` FK `users` ON DELETE SET NULL, nullable | фиксированный владелец заявок этого сайта |
| `contact_task_sla_hours` | `Integer` NOT NULL default `2` | через сколько часов дедлайн задачи «Связаться» |
| `source_label` | `String(120)` nullable | человекочитаемое имя канала для аналитики (фолбэк — `name`) |

Без новых таблиц. `FormSubmission` уже хранит всё для аналитики.

### 4.2. Приём заявки — `app/forms/public_routers.py::submit_form`

Добавить проверку ключа **перед** созданием лида, после rate-limit:

```
if form.ingest_token:
    provided = request.headers.get("x-form-key")
    if not provided or not hmac.compare_digest(provided, form.ingest_token):
        raise HTTPException(401, "Неверный или отсутствующий ключ формы")
```

`hmac.compare_digest` — против тайминг-атак. Остальной флоу не меняется.

### 4.3. Маршрутизация + задача — `app/forms/lead_factory.py::create_lead_from_submission`

После `session.flush()` лида:

```
if form.default_assignee_id:
    lead.assignment_status = "assigned"
    lead.assigned_to = form.default_assignee_id
    lead.assigned_at = now_utc()
    session.add(Activity(
        lead_id=lead.id, user_id=None, type="task",
        body="Связаться с заявкой",
        task_due_at=now_utc() + timedelta(hours=form.contact_task_sla_hours),
    ))
```

- задача — `Activity(type=task)` с `task_due_at` (обязателен для type=task), детер-
  минированная, **не AI** — попадает в `/me/tasks` и `/today` владельца, т.к. лид
  на него назначен;
- если `default_assignee_id` пуст → ветка не выполняется, лид остаётся в пуле
  (текущее поведение полностью сохранено).

Поле `body`/колонки задачи свериться с реальной схемой `Activity` (`task_due_at`,
`task_done`, `body`) на этапе реализации.

### 4.4. Уведомление владельца — `public_routers._notify_workspace_admins`

Если у формы есть `default_assignee_id`, дополнительно дёрнуть `safe_notify` с
`user_id=default_assignee_id` (`kind="system"`, заголовок «Новая заявка с сайта»,
`lead_id`). Best-effort, как и админ-уведомления.

### 4.5. Админ-API — `app/forms/{schemas,services,routers}.py`

- `WebFormCreateIn` / `WebFormUpdateIn`: добавить `default_assignee_id`,
  `contact_task_sla_hours` (ge=1, le=240), `source_label`.
- Валидация в `services.create_form` / `update_form`: `default_assignee_id` должен
  принадлежать workspace вызывающего (иначе `WebFormInvalidTarget`-подобная 400).
- `ingest_token`: у формы есть булев флаг «защищённый приём (S2S)». При включении
  (на create или update) сервер генерирует `secrets.token_urlsafe(32)` и пишет в
  `ingest_token`; при выключении — обнуляет (форма снова открытая). Отдельный
  `POST /api/forms/{id}/rotate-key` перевыпускает ключ. Дефолт для новых форм —
  выключено (NULL), чтобы поведение по умолчанию оставалось открытым/совместимым.
  `ingest_token` возвращается в `WebFormOut` **только админу/head**.
- `WebFormOut`: новые поля + `ingest_token` (для копирования в бэкенд сайта).

### 4.6. Аналитика по каналам — `GET /api/forms/analytics`

Новый read-эндпоинт (любой авторизованный в workspace), агрегирует по формам за
период `?from=&to=`:

| Поле | Источник |
|---|---|
| `form_id`, `source_label` (или `name`) | `web_forms` |
| `submissions` | `count(form_submissions)` за период |
| `leads` | `count(distinct lead_id)` |
| `won` | join `leads.won_at IS NOT NULL` |
| `conversion` | `won / leads` |

Отдаёт список строк (по форме) + итог. Используется на странице `/forms`.

### 4.7. Фронтенд — `apps/web`

- `components/forms/FormEditor.tsx`: селект «Ответственный менеджер» (список
  пользователей workspace), числовое «SLA, часов» (дефолт 2), поле «Название
  канала». Блок «Интеграция»: показать `ingest_token`, готовый `<script>`-сниппет
  и пример server-to-server `curl`.
- `app/(app)/forms/page.tsx`: таблица аналитики по каналам (из 4.6).
- хук `lib/hooks/use-forms.ts`: добавить новые поля + запрос аналитики.

### 4.8. Документация контракта для разработчиков сайтов

`docs/integrations/website-forms-api.md` — то, что отдаём фронтендерам сайтов:

- URL: `POST https://crm.drinkx.tech/api/public/forms/{slug}/submit`
- Заголовки: `Content-Type: application/json`, `X-Form-Key: <ключ сайта>`
- Тело (JSON): канонические ключи (`company_name`/`название`, `email`/`почта`,
  `phone`/`телефон`, `city`/`город`, `inn`/`инн`, `comment`/`сообщение`) + любые
  `utm_*`. Неизвестные ключи сохраняются в `raw_payload`.
- Ответы: `200 {ok:true, redirect}` / `401` неверный ключ / `404` нет формы /
  `410` форма выключена / `429` rate-limit.
- Пример `curl` и узел Node.js (бэкенд сайта шлёт после отправки письма).

## 5. Границы (что НЕ делаем)

- Не шлём письма на почту отдела — это на стороне сайтов (по решению заказчика).
- Не делаем round-robin/territory-роутинг — только фиксированный владелец
  (архитектуру `assigned_to` это не блокирует, добавим позже при необходимости).
- Не трогаем embed.js по существу (он продолжает работать для открытых форм);
  по желанию добавим в него поддержку `X-Form-Key` — но для форм с ключом
  правильный путь именно S2S с бэкенда, не браузер.

## 6. План тестов (pytest, mock-only)

1. `submit_form` с `ingest_token`: верный ключ → 200; неверный/нет → 401; форма
   без токена → 200 (обратная совместимость).
2. `create_lead_from_submission`: с `default_assignee_id` → лид `assigned` +
   создана `Activity(type=task)` с корректным `task_due_at`; без него → лид в пуле,
   задачи нет.
3. SLA: `task_due_at == created + sla_hours`.
4. Админ-валидация: `default_assignee_id` чужого workspace → 400; `sla` вне границ
   → 422.
5. Аналитика: агрегаты submissions/leads/won за период считаются верно.
6. Уведомление владельцу шлётся при назначении (мок `safe_notify`).

## 7. Критерии готовности

- [ ] Миграция 0041 применяется и откатывается чисто.
- [ ] Заявка с сайта с заданным владельцем → лид `assigned` + задача «Связаться»
      видна владельцу в `/today` и `/me/tasks`.
- [ ] Заявка без владельца → лид в пуле (старое поведение не сломано).
- [ ] Submit с `ingest_token` отклоняет неверный ключ (401).
- [ ] `/forms` показывает аналитику по каналам.
- [ ] `docs/integrations/website-forms-api.md` готов и самодостаточен.
- [ ] `pytest` зелёный; `pnpm build` в `apps/web` проходит.
