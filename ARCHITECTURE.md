# DrinkX Smart AI CRM — Архитектура, экраны, стек, проблемы

> Снимок на 2026-06-07. Обзорный документ: что за продукт, какие экраны/разделы,
> какой стек, и где сейчас болит. Детали — в `docs/PRD-v2.0.md` (продукт),
> `docs/brain/` (исполнение), `docs/brain/01_ARCHITECTURE.md` (внутренняя архитектура),
> `CRM_AUDIT_REPORT.md` и `docs/UX_AUDIT_2026-05-23.md` (аудиты).

## Что это

B2B CRM для DrinkX — продаёт умные кофе-станции в ритейл / HoReCa / QSR / АЗС.
Продакшн: https://crm.drinkx.tech (живой, авто-деплой при push в `main`).
Роли пользователей: **admin**, **head** (руководитель), **manager** (менеджер).

---

## Стек

### Frontend (`apps/web`)
- **Next.js 15** (App Router, `typedRoutes`), **React 19**, **TypeScript strict**.
- **Tailwind CSS** + **shadcn/ui** (Radix: dropdown-menu, slot, tabs, tooltip).
- **TanStack Query** (server state) + **TanStack Table** (таблицы).
- **Zustand** (client state).
- **@dnd-kit** (drag-and-drop: канбан `/pipeline`, виджеты `/today`).
- **Recharts** (графики `/forecast`).
- **lucide-react** (иконки), **CVA + clsx + tailwind-merge** (варианты классов).
- **@supabase/ssr** + **supabase-js** (auth-сессия, JWT).
- Тесты: **vitest**. Линт: **eslint** (+ кастомное правило `drinkx/no-arbitrary-px`).

### Backend (`apps/api`)
- **FastAPI** (async-first, Python 3.12) + **uvicorn**.
- **SQLAlchemy 2 (async)** + **asyncpg**, миграции **Alembic** (head `0045`).
- **Pydantic v2** + pydantic-settings.
- **Celery + Redis** (фоновые/AI-задачи; долгие задачи не блокируют REST — POST→202→WS).
- **python-jose** (JWT), **cryptography**, **google-auth** (+ OAuth, api-client).
- **httpx**, **structlog**, **sentry-sdk**, **aiosmtplib** (email),
  **openpyxl** (xlsx), **pypdf**, **feedparser**, **phonenumbers** (E.164).
- Качество: **ruff**, **mypy --strict**, **pytest** (+ CI на postgres:16).
- Архитектура — **package-per-domain** (НЕ слоёная): каждый домен = `models.py`,
  `schemas.py`, `repositories.py`, `services.py`, `tasks.py`, `routers.py`, `events.py`.

### Инфраструктура / внешние сервисы
- **Supabase** — Postgres + Auth + Storage.
- **Upstash Redis** — брокер/бэкенд Celery.
- **DeepSeek** — основной LLM; **OpenAI** — vision / дорогие корзины.
- **Brave Search** — веб-ресёрч; **HH.ru** — сигнал вакансий; **Apify** (Phase 1.5+) — скраперы.
- **Google OAuth** — вход; **Sentry** — ошибки.
- **Деплой**: bare-metal `crm.drinkx.tech` (77.105.168.227), **docker compose**
  (`web`, `api`, `worker`, `beat`), **GitHub Actions** `deploy.yml` при push в `main`
  → `infra/production/deploy.sh` (git pull → build → health-check `/health`).
  НЕ Vercel/Railway. PR-preview-окружения нет.

---

## Экраны и разделы

### Основная навигация (левый сайдбар)
Порядок сверху вниз; гейтинг по роли — на этапе сборки меню
(`apps/web/components/layout/SidebarNavContainer.tsx`).

| Пункт меню | Роут | Доступ | Назначение |
|---|---|---|---|
| Поиск (⌘K) | — (модалка) | все | глобальный поиск |
| Сегодня | `/today` | все | дашборд: задачи, счётчики, стадии воронки, уведомления, напоминания (DnD-виджеты) |
| Задачи | `/tasks` | все | список задач менеджера (фильтры статус/срок) |
| Прогноз | `/forecast` | все | взвешенный прогноз, риски, каналы привлечения (UTM), графики |
| Воронка | `/pipeline` | все | канбан сделок по этапам (DnD) |
| Входящие | `/incoming` | все | заявки с веб-форм (бейдж новых) |
| База лидов | `/leads-pool` | все | пул лидов, claim, «не лид» |
| Мессенджеры | `/triage` | все | сообщения без привязки к лиду (Telegram/MAX/телефон) |
| Формы | `/forms` | **admin/head** | конструктор веб-форм + аналитика по каналам |
| Автоматизации | `/automations` | **admin/head** | builder автоматизаций |
| Команда | `/team` (admin/head) / `/settings?section=team` | все | дашборд активности/нагрузки команды |
| База знаний | `/knowledge` | все | плейбуки/скрипты (раздел в разработке — заглушка) |
| Руководство | `/guide` | все | онбординг/справка |
| Журнал | `/audit` | **admin** | журнал изменений (audit log) |
| Уведомления | — (drawer) | все | дровер уведомлений (бейдж непрочитанных) |
| Настройки | `/settings` | все | воронки, команда, каналы, AI, расходы, кастом-поля, шаблоны, внешний вид, обновление базы |

### Детальные / служебные роуты (не в основном меню)
| Роут | Назначение |
|---|---|
| `/leads/[id]` | **Карточка лида** — центральный экран. Внутри вкладки: лента/фид, задачи, контакты (`ContactsTab`), файлы, кастом-поля, AI-агент «Блейк» |
| `/companies`, `/companies/[id]` | компании (роут есть, в основном меню отсутствует) |
| `/team/[user_id]` | карточка участника команды |
| `/settings/profile` | профиль пользователя (отдельный роут) |
| `/sign-in`, `/auth/callback` | вход (Google OAuth, magic-link, тест-вход) и OAuth-callback |

Глобальные оверлеи: `NotificationsDrawer`, мастер импорта (`ImportWizardMount`),
командная палитра поиска (⌘K), модалки (создание/редактирование форм, задач, подтверждения).

---

## Backend-домены (`apps/api/app`)

`activity`, `assignment`, `audit`, `auth`, `automation`, `automation_builder`,
`base_update`, `common`, `companies`, `contacts`, `custom_attributes`,
`daily_plan`, `email`, `enrichment`, `followups`, `forms`, `import_export`,
`inbox`, `knowledge`, `lead_agent`, `leads`, `llm_usage`, `notes`,
`notifications`, `pipelines`, `quotas`, `quote`, `reminders`, `scheduled`,
`search`, `settings`, `storage`, `team`, `template`, `users`, `utm`.

Сервисная инфраструктура: `config.py`, `db.py`, `main.py`, `observability.py`.
Переходы по этапам идут через `app/automation/stage_change.py` (pre/post-хуки).

---

## Архитектурные принципы и анти-паттерны (guardrails из CLAUDE.md)

**Нельзя вводить:** синхронный REST для долгих AI-задач; LLM с сырым SQL (только
whitelisted-вьюхи); мульти-агент ради мульти-агента; авто-действия AI без human-in-the-loop;
DSL-метаданные на всё; монолитные `cron/`-скрипты (только Celery beat с явным реестром);
output-схемы без fallback-дефолтов (Pydantic AI-выходы — `Optional` + defaults, не падать на missing).

---

## Известные проблемы

Помечено: **[открыто]** — актуально; **[чинится]** — в работе/на ветке;
**[исправлено]** — закрыто в этой сессии; источник — где найдено.

### Дизайн / UX
- **[чинится] Стратегия ширины.** Единый кэп `1280px` по центру → на широких
  мониторах большие пустые поля по бокам. PR #129 (`ui/unify-page-layout`)
  унифицировал ширину 10 экранов, но `fixed centered` не оптимален для wide-дисплеев.
  Идёт редизайн на fluid-ширину (taste-skill). *(эта сессия)*
- **[открыто] Два визуальных языка карточек.** Исторически: legacy
  `border-black/5` + `rounded-2xl` + `shadow-soft` ↔ дизайн-система
  `border-brand-border` + `rounded-[2rem]`. PR #129 свёл основные 10 экранов к
  дизайн-системе; осталось в компонентах: `UnmatchedMessagesSection` (triage),
  nav `/settings`, карточка `/sign-in`, внутренности `FormEditor`. *(эта сессия)*
- **[открыто] Мелкий текст.** Бейджи `text-[10px]/[11px]` на грани читаемости. *(аудит 2026-05-22)*
- **[открыто] ~235 мест с arbitrary-px.** Есть warn-lint `drinkx/no-arbitrary-px`,
  массовая зачистка отложена (`docs/BACKLOG.md` #3). *(00_CURRENT_STATE)*
- **[открыто] `/leads-pool`:** `page_size=500` + фильтрация на клиенте → при >500
  лидов часть **молча не видна**; нет пользовательской сортировки, нет мультивыбора/
  массовых действий; «Не лид» через нативный `window.confirm`. *(аудит 2026-05-22)*
- **[открыто] Карточка лида `/leads/[id]`:** перегруженная шапка — деструктивное
  «Удалить» рядом с частыми кнопками; inline-правка имени компании неочевидна. *(аудит 2026-05-22)*
- **[открыто] Контакты (вкладка):** `<li role="button">` (несемантично, хуже для
  скринридеров); соц-ссылки Instagram/Facebook — UI-заглушки без бэкенда. *(аудит 2026-05-22)*
- **[открыто] `/pipeline`:** DnD только указателем (нет клавиатуры); нет undo после
  перетаскивания. *(аудит 2026-05-22)*
- **[открыто] `/settings/profile`:** слабый фидбек сохранения (текст кнопки на 2с, без тоста). *(аудит 2026-05-22)*

### Frontend-код
- **[исправлено] `rose-600`/`rose-500` не резолвились.** В `tailwind.config.ts`
  `rose` = строка без числовой шкалы → кнопка удаления формы рендерилась без фона
  (невидимая). Заменено на `rose` в 4 файлах; подтверждено в собранном CSS
  (`.bg-rose` → `#B23A48`). *(эта сессия)*
- **[открыто] `LeadCard` — 617-строчный компонент.** Сплит отложен (`docs/BACKLOG.md`). *(00_CURRENT_STATE)*
- **[открыто] `typedRoutes` deprecation.** Next предупреждает: `experimental.typedRoutes`
  переехал в `typedRoutes` — обновить `next.config.mjs`. *(эта сессия, dev-лог)*

### Безопасность
- **[закрыто] Хардкод тест-кредов.** Кнопка «🧪 Войти как тестовый пользователь»
  в `apps/web/app/sign-in/page.tsx` больше не содержит креды: они читаются из
  `NEXT_PUBLIC_TEST_LOGIN_EMAIL` / `NEXT_PUBLIC_TEST_LOGIN_PASSWORD`, которые
  задаются только в локальном `.env.local`. Без них кнопка не рендерится и
  пароль не попадает в прод-бандл. *(2026-07-14)*
- Рекомендуется отдельный security-review (этой сессией глубоко не аудировано).

### DX / инфраструктура
- **[открыто] Неполный локальный env.** `apps/web/.env.local` не содержит
  `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` → локальный
  логин без них не работает. Добавить в `.env.local.example`. *(эта сессия)*
- **[открыто] Несколько lockfile'ов.** `~/package-lock.json` + репозиторный
  `pnpm-lock.yaml` → Next выбирает неверный workspace root (warning). Зафиксировать
  `outputFileTracingRoot` или убрать лишний lockfile. *(эта сессия, dev-лог)*
- **[открыто] Untracked-артефакты в корне.** `.beads/`, `CRM_AUDIT_REPORT.md`,
  `scripts/lpr_import/`, `.agents/skills/` — не в `.gitignore` и не закоммичены. *(git status)*

### Backend
- Явных нарушений в этой сессии не найдено. Соблюдать guardrails выше
  (async для AI-задач, fallback-дефолты в схемах, Celery beat вместо cron-скриптов).

---

## Где что искать
- Продукт: `docs/PRD-v2.0.md` · Лид-пул: `docs/PRD-addition-v2.1-lead-pool.md`
- Текущее состояние / следующий спринт: `docs/brain/00_CURRENT_STATE.md`, `04_NEXT_SPRINT.md`
- Внутренняя архитектура / решения: `docs/brain/01_ARCHITECTURE.md`, `03_DECISIONS.md`
- Аудиты: `CRM_AUDIT_REPORT.md` (2026-05-22), `docs/UX_AUDIT_2026-05-23.md`
- Бэклог: `docs/BACKLOG.md`
