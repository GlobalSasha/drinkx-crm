# DrinkX CRM — Glossary

**DrinkX** — компания, производит умные кофе-станции для B2B.
Сегменты: HoReCa / Ритейл / QSR / АЗС / Офис / Партнёры.

**ICP** — Ideal Customer Profile.
Цель: сети 10+ точек, боль — нехватка бариста или нестабильное качество.

**fit_score (0–10)** — AI-оценка соответствия ICP.
Считает Research Agent автоматически. **НЕ путать со Score 0–100.**

**Score (0–100)** — управленческий scoring сделки.
Заполняет менеджер вручную по 8 критериям с весами.
Определяет Tier A/B/C/D приоритет.

**Priority A/B/C/D**
- A = Стратегический (Score 80–100, личное управление)
- B = Перспективный (60–79, активная работа)
- C = Низкий приоритет (40–59, nurture)
- D = Архив (<40, автообработка)

**Gate** — чеклист условий при переходе между стадиями.
Открывается как модал. Уникален для каждого перехода.

**Rotting** — сделка без прогресса, **два независимых правила**:
- Stage-rot: слишком долго в одной стадии (> rot_days)
- Next-step-rot: нет задачи или просрочена (3д = жёлтый, 7д = красный)

**Research Agent** — AI-агент обогащения карточки.
Источники: BraveSearch + HH.ru + Apify + web_fetch.
Запускается при создании лида, пишет в `lead.ai_data`.

**Daily Plan** — AI-план дня менеджера.
Генерируется Celery cron в 08:00 timezone воркспейса.

**Sales Coach** — AI-ассистент в карточке лида.
Знает: текущую стадию + gate статус + KB + drinkx_profile.yaml.
Правило: предлагает → менеджер аппрувит, никаких автодействий.

**Assignment Engine** — алгоритм распределения лидов по менеджерам.
Учитывает: нагрузку (40%) + экспертизу (30%) + часовой пояс (20%) + баланс (10%).

**Inbox Matching** — привязка входящих сообщений к лидам.
Email → `lead.email` / TG → `lead.telegram_id` / WA → `lead.phone`.

**Champion** — контакт в компании клиента, двигающий сделку изнутри.

**Economic Buyer** — контакт с правом подписи бюджета.
Обязателен с Stage 6. Блокирует Gate Stage 7 если не выявлен.

**Pilot Success Contract** — документ с метриками пилота.
Вкладка в карточке лида, активируется при Stage 9+.

**Pipeline Review** — еженедельная структурированная встреча по воронке.
45 минут, повестка: новые лиды / Tier 1 / красные / партнёры / прогноз 30/60/90.

**Lead Pool** — общий пул лидов воркспейса (PRD addition v2.1).
Менеджеры берут карточки порциями (sprint) через "Сформировать план на неделю".
Race-safe optimistic locking.

**Weekly Sprint** — недельная порция лидов одного менеджера.
N = `workspace.sprint_capacity_per_week` (default 20).

**Deal Type** — обязательное поле, 6 значений:
Прямой enterprise / QSR / Дистрибьютор-партнёр / Сырьевой / Частный малый /
Сервис повторная.

**taste-soft** — дизайн-система CRM прототипа.
Plus Jakarta Sans + JetBrains Mono, silver canvas, double-bezel cards,
squircle radii, custom cubic-bezier transitions.

**HoReCa** — Hotels, Restaurants, Cafes (ключевой сегмент DrinkX).
**QSR** — Quick Service Restaurant (McDonald's / KFC tier).
**EAV** — Entity-Attribute-Value (паттерн для кастом-полей).
**KB** — Knowledge Base (playbooks, success stories, objections, competitors).
**RLS** — Row-Level Security (Postgres / Supabase feature for multi-tenancy).

## Naming conventions in code

- `lead_id` — UUID
- `next_action_at` — TIMESTAMPTZ (nullable)
- `assignment_status` — ENUM('pool', 'assigned', 'transferred')
- `role_type` (contact) — ENUM('economic_buyer', 'champion', 'technical_buyer', 'operational_buyer')
- `deal_type` (lead) — ENUM (6 values listed above)
- `priority` (lead) — ENUM('A', 'B', 'C', 'D')
- `score` (lead) — INT 0–100
- `fit_score` (lead) — INT 0–10 (nullable until enrichment runs)

## Stub-mode markers in code
- `SUPABASE_JWT_SECRET=""` → `verify_token` returns `_stub_claims()`
- Stub identity: `dev@drinkx.tech`, sub `00000000-0000-0000-0000-000000000001`
- Stub mode is logged in `TokenClaims.is_stub = True` so dev/staging/prod paths can branch
