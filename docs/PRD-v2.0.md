# PRD: Smart AI CRM (DrinkX) — v2.0

**Базируется на:** PRD v1.3 + PRD-additions v1.4 + всё что добавлено в Phase 0 прототипе
**Дата:** 2026-05-05
**Автор:** Alexander Khvastunov (DrinkX)
**Статус:** консолидированная редакция перед стартом разработки
**Phase 0 прототип:** https://globalsasha.github.io/drinkx-crm-prototype/index-soft-full.html
**GitHub:** https://github.com/GlobalSasha/drinkx-crm-prototype

---

## 1. Problem Statement

Существующие CRM (AmoCRM, Bitrix24, Zoho) хранят данные, но не дают интеллекта. Менеджер тратит 30-40% времени на ручной поиск информации о лидах, приоритизацию, планирование. Система не знает что у компании сменился CTO или прошёл раунд.

**3 ключевых pain point:**
1. Данные карточки устаревают — менеджер работает со stale info
2. Нет распределения нагрузки — «кто успел, тот и взял»
3. Нет стратегических рекомендаций — менеджер действует интуитивно

## 2. Goals (MVP)

- Канбан/воронка с карточками лидов (feature parity с AmoCRM баз)
- AI-обогащение каждой карточки актуальными данными из внешних источников
- AI-рекомендации стратегических следующих шагов
- Онбординг через Google OAuth
- Unified Inbox: Email + Telegram Business внутри карточки
- Импорт лидов из Bitrix24 + bulk-update workflow от внешнего AI
- Автоматическое распределение лидов между менеджерами с учётом рабочего времени
- **Activity feed как сердце карточки** — комментарии, задачи, напоминания, файлы, авто-события
- **Follow-up sequences** — настраиваемые этапы воронки с автоматическими напоминаниями
- **AI Brief side drawer** — быстрый просмотр без полного перехода
- Multi-pipeline (новые / повторные / партнёры)
- Editable ЛПР cards с верификацией
- Knowledge Base для AI-grounding (playbooks, success stories, объекции, конкуренты)
- WebForm builder с UTM-захватом
- Notifications (in-app + email + push + Telegram)

## 3. Non-Goals (v1.0)

- Мобильное приложение (только web; mobile-first responsive)
- VoIP / телефония
- Автоматическая отправка сообщений без участия менеджера (AI предлагает — менеджер аппрувит)
- Финансовая аналитика и биллинг
- MCP-сервер для внешних AI-агентов (Phase 2 / v1.5)

## 4. Users & Personas

| Персона | Роль | Ключевые задачи |
|---|---|---|
| Менеджер | sales | работа с назначенными карточками, ответы на сообщения, фиксация активностей, follow-up по этапам, ответы на AI-подсказки |
| Руководитель отдела продаж | head | дашборд команды, перераспределение нагрузки, аналитика конверсии, работа с Knowledge Base |
| Суперадмин / Owner | admin | настройки workspace, тарифы, AI-провайдеры, audit log |

## 5. Information Architecture

### 5.1 Today-first IA (выбран в Phase 0)

```
Sidebar (sticky)
├── 📋 Today (главный экран — AI-приоритизированный план дня)
├── 📊 Pipeline (Kanban — drag-drop, scroll page-level + per-column)
├── 💬 Inbox (глобальный — unmatched messages + per-lead в карточках)
├── 📦 Архив
├── 👥 Команда (head only)
├── 📚 Knowledge (head only)
├── 🗺️ Сегменты (head only)
└── ⚙️ Настройки (head only)

Floating elements:
├── 🔔 Notification bell (top-right) с drawer
└── 🤖 AI Coach FAB (bottom-right, на карточке) с drawer
```

### 5.2 Принцип Today-first

- Менеджер открывает CRM → сразу видит «делать вот это, по порядку»
- Pipeline = карта (вторичный обзор)
- Карточка = место работы
- Не три равноправных экрана, а иерархия: «делать → смотреть → редактировать»

## 6. Core Screens & Features

### 6.1 Today (Daily Plan)

**Назначение:** утренний экран менеджера, готовый AI-план дня.

**Состав:**
- Шапка: «Доброе утро, {имя}» + дата + N задач
- Расчёт нагрузки: «Доступно X ч / Загружено Y ч / Z%» + прогресс-бар
- 3 группы задач:
  - 🔥 **Срочно** (red) — дедлайн / обещание сегодня / горящий момент
  - ⚡ **Приоритет** (orange) — rotting / горячие / новые с высоким fit
  - 📋 **Плановое** (blue) — регулярное продвижение
- Каждая задача: компания + стадия + сумма+масштаб + 🤖 AI-подсказка (1-2 строки) + время + причина приоритета

**Empty states:**
- «Всё сделано» — celebratory + AI-предложения опережающих действий
- «Пусто (новый менеджер)» — onboarding CTAs

### 6.2 Pipeline / Kanban

**Состав:**
- Top bar: переключатель воронки + stats (X сделок · ₽YM · Z rotting) + view (Kanban/List/Focus) + actions (Фильтры / Импорт / Экспорт / + Лид)
- Filter rows:
  - **Сегмент:** все / ритейл / non-food / кофейня / QSR / АЗС / дистр
  - **Город:** все / Москва / СПб / Екатеринбург / ... (top 12 by lead count)
  - **Поиск:** instant фильтр по названию + описанию
- 🤖 **AI-баннер «Сигналы дня»** — горизонтально 3 главных алерта пайплайна
- Доска: 6 колонок (Новые лиды → Квалификация → КП отправлено → Переговоры → Согласование → Закрыто (won)) + опциональная Closed (lost)
- **Page-level scroll** + per-column scroll (внутри колонки) — обе работают одновременно
- Карточка лида: название · fit-score (цветной pill 0-10) · сумма+масштаб · теги (urgent/rotting/hot/new) · аватар ответственного · AI-flag (🔥/⚡/NEW) для критичных

**Drag-drop:** карточки переносятся между стадиями. Won → модалка с финальной суммой, что сработало (chips для KB), заметкой. Lost → причина + комментарий.

### 6.3 Lead Card

**4 таба:**
- 📋 **Информация** (поля + редактирование)
- 💬 **Переписка** (Unified Inbox — Email + TG)
- 🤖 **AI Brief** ★ (default tab)
- 📑 **КП** (Quote builder)
- 🕐 **Активности** (полная лента, центральный workspace)

#### 6.3.1 Layout

- Header: компания · стадия pill · сумма · ответственный · источник · дата + actions (⋯ / Переместить / + Активность)
- Body: 2 колонки
  - **Левая (280px):** компания, сайт, сегмент, **редактируемые ЛПР-карточки**, теги
  - **Правая:** контент активной вкладки

#### 6.3.2 ЛПР как редактируемые карточки (новое)

- Hover → ✏ иконка, click → модалка редактирования
- Поля: ФИО · должность · роль для DrinkX (8 типов: owner / operations / procurement / category_manager / foodservice / partnerships / marketing / legal) · email · телефон/Telegram · LinkedIn URL · источник · уверенность (high/med/low) · статус (✓ verified / ⏳ to-verify)
- «+ Добавить» кнопки для двух bucket'ов (Контакты ЛПР / На проверку)
- Move from to-verify → verified
- Хранятся в `lead.contacts[]`

#### 6.3.3 AI Brief (default tab)

- **Score header:** drinkx_fit_score (0-10) + вердикт + время обогащения + «↻ обновить»
- 🏢 **Профиль компании** (2-3 предложения с источниками)
- 📏 **Масштаб** (точки, города, форматы)
- ☕ **Кофе/foodservice сигналы**
- 📊 **Sales triggers** (2x2 grid: рост / возможность / ⚠️ риск)
- 🏭 **Industry-слой** (отдельный enrichment v0.4)
- 🎯 **Контакты ЛПР** (LinkedIn + DM)
- 👥 **Дополнительные ЛПР** (industry research)
- 🚪 **Точка входа**
- ⚠️ **Research gaps** (что AI не нашёл, честно)
- 📚 **Источники AI** (clickable pills)
- 🎬 **Рекомендованные шаги** (нумерованный 3-пункта список с action кнопками)

#### 6.3.4 Activity feed (🕐 Активности — центральная фича)

**Это главное место работы менеджера в карточке.** В ленте живут:
- 💬 Комментарии (заметки менеджера)
- 📋 Задачи (с due_at, assignee, status pending/done)
- 🔔 Напоминания (trigger_at, kind: manager / auto_email / ai_hint)
- 📎 Файлы (attached: КП, презентация, договор, фото; КП дополнительно генерит system event)
- 📧 Email / 💙 Telegram (зеркала из Inbox)
- ⚙ Системные события (создание лида, AI обогащение, переход стадии, drag-drop won/lost, bulk import, отметка follow-up done)

**Композер сверху:** 4 режима-tab'а
- 💬 Комментарий — textarea
- 📋 Задача — textarea + due date + assignee
- 🔔 Напоминание — textarea + trigger date + type (manager / auto_email / ai_hint)
- 📎 Файл — filename + type (КП/Презентация/Договор/Фото/Другое) + комментарий

**Quick actions:** 📎 Прикрепить · @ упомянуть · 🤖 AI-черновик (генерит draft из AI Brief)

**Filter chips:** Все / 💬 Комментарии / 📋 Задачи / 🔔 Напоминания / 📎 Файлы / ⚙ Системные

**Item actions:** ✓ Mark done (для задач) · 🗑 Удалить · ✏ Edit (плановое расширение)

#### 6.3.5 Follow-up sequences (новое — над Activity feed)

**Этапы воронки и напоминания** — настраиваемая последовательность.

Структура: `lead.followups[]` с полями:
- name (название этапа)
- due (дата)
- status (done / active / pending / overdue)
- reminder type (manager / auto_email / ai_hint)
- notes (опционально)

**Auto-seed на основе stage:**
- Новые лиды → Первый контакт → Квалификация → Отправка КП
- Квалификация → Discovery → Отправить КП → Follow-up по КП
- КП отправлено → Follow-up по КП (active) → Назначить демо
- Переговоры → Согласовать условия → Подписание
- Согласование → Договор отправлен → Подписание → Старт пилота

**Visual:** vertical timeline с маркерами (✓ done / ● active / ○ pending / ! overdue), цветной gradient track, due date (mono font), reminder badge.

**Actions:** ✓ Mark done (auto-promote next pending → active + push system event), ✏ Edit name/date, 🗑 Delete, + Add stage.

**Reminder behavior:**
- `manager` — на due date в Today появляется задача с AI-подсказкой («сегодня пятница, надо напомнить N о КП»)
- `auto_email` — система отправляет email шаблон с переменными `{{lead.name}}`, `{{contact.name}}`, etc. Менеджер аппрувит черновик перед отправкой (anti-spam policy).
- `ai_hint` — за день до due AI готовит контекст-помощник к звонку

### 6.4 Brief Side Drawer (новое)

**Назначение:** в Pipeline клик на любую карточку открывает компактный AI Brief drawer справа, **без полного перехода** на Lead Card screen.

**Структура drawer'а:**
- Header: стадия · Tier · название · meta (₽сумма · сегмент · 📍города · 👤менеджер · ⚠ rotting если есть)
- Body:
  - Verdict box (fit_score + краткий вердикт)
  - 🎬 «Что делать сейчас» — нумерованный 3-4 пункта (Сегодня / Дальше / Потом)
  - ☕ Coffee signals
  - 🎯 ЛПР (top 4)
  - 📏 Масштаб
  - 📊 Sales triggers
- Footer: ← Предыдущий · **Открыть карточку полностью →** · Следующий →

**Навигация:** Esc / клик по overlay = закрыть; ←/→ стрелки = prev/next по отфильтрованному списку Pipeline

**Зачем:** менеджер за 30 секунд видит «что у него стоит дальше / что потом / что сейчас» — без полного перехода. Если нужно работать в карточке → «Открыть полностью» открывает full screen.

### 6.5 Unified Inbox

**Поддерживаемые каналы:**

| Канал | MVP | Протокол | Примечание |
|---|---|---|---|
| Email | ✅ | IMAP idle (входящие) + SMTP (исходящие) + Gmail API push | Gmail, Яндекс, корп Exchange |
| Telegram Business | ✅ | Telegram Business API (официальный) | Только Premium Business аккаунт |
| WhatsApp Business | Phase 2 | Meta Cloud API | Нужен верифицированный номер |
| VK Messaging | Phase 2 | VK API | Для РФ-сегмента |

**Внутри карточки:** единая лента всех каналов (filter chips: Все / Email / TG / WA), composer внизу с переключателем канала + AI «Сгенерировать ответ на основе AI Brief».

**Глобальный Inbox:** unmatched messages (входящие, которые AI не смог matchить с лидами) → менеджер вручную привязывает или создаёт новый лид.

**Matching logic:** email → from_address → lead.email; TG → user_id/username → lead.telegram_id; WA → phone → lead.phone (с нормализацией). Не найдено → unmatched bucket.

### 6.6 Quote / КП (📑 таб в карточке)

**Состав:**
- История КП (sent / accepted / rejected / draft) — список с суммой и статусом
- Текущий черновик (builder):
  - Header: получатель · действует до · шаблон · actions (PDF / Email превью / Отправить)
  - Meta: получатель, действует до, шаблон
  - Таблица позиций (модели DrinkX-станций + сервисный пакет + монтаж + опции)
  - **🤖 AI-подсказка:** на основе AI Brief предлагает добавить опции (например brand-customization для franchise-сетей)
  - Totals: позиции − скидка + НДС = ИТОГО
  - Footer: автосохранено + автор + дублировать / черновик

**Сущности:** quotes, quote_lines (см. data model)

### 6.7 Workload Distribution (AI Assignment Engine)

**Это уникальная фича** — ни в одной из 17 исследованных open-source CRM нет.

**Алгоритм:**
```
Score(manager, lead) =
  (1 - current_load) × 0.4          // доступность
  + expertise_match(manager, lead) × 0.3  // опыт с похожими сделками
  + time_zone_match × 0.2            // совпадение часового пояса
  + round_robin_fairness × 0.1       // выравнивание
```

**Расчёт нагрузки:** `current_load = (active_cards × avg_weight) / (work_hours_today × productivity_coef)`. Вес: hot=2.0x, normal=1.0x, low=0.5x.

**Pluggable стратегии (модуль `app/assignment/`):**
- RoundRobinStrategy
- WorkloadBasedStrategy
- ExpertiseBasedStrategy (по sales history + сегменту)
- HybridStrategy (current — комбинация)

**Daily Plan generation (cron 08:00 workspace TZ):**
1. Для каждого менеджера: получить рабочие часы, активные лиды
2. PriorityScorer: urgency × deal_size × stage_probability × ai_data.urgency_score
3. Упаковать N задач в дневной план (fit в часы)
4. LLM генерит «task hint» (1 строка) под каждую
5. Сохранить DailyPlan в БД
6. Notify менеджера (email digest + in-app + Telegram)

### 6.8 Team View (Head of Sales)

- Top stats: 3 менеджера · X сделок · ₽YM · конв % · Z won
- 🤖 AI-алерты: перегрузки, простои, rotting без задач, медленные стадии
- 3 строки менеджеров: avatar · роль · спецификация · метрики (load%, deal total, conversion, rotting) + actions (Pipeline / Профиль / Перераспределить → / Назначить лидов →)
- Conversion funnel (visual)
- Heatmap нагрузки по дням недели

### 6.9 Knowledge Base (admin)

**Категории:**
- 📋 Playbooks (по сегментам: HoReCa, ритейл, QSR, АЗС, офис, франшиза)
- ⭐ Success stories
- ⚠️ Объекции (типовые возражения с ответами)
- 🥊 Конкуренты (Drive Café, LukCafe, Зерно — слабости/сильные/угол)
- 📦 Продукт (модели станций, характеристики, цены)
- 🏢 Профиль DrinkX (profile.yaml, icp.yaml, tone.yaml)

**UI:** 3 колонки (Категории / Файлы / Editor markdown). Файл имеет теги для AI-матчинга (`сегмент: HoReCa`, `тип: кофейная сеть`, `стадия: Квалификация`). Внизу editor — usage tracking (какие карточки использовали этот файл за 7 дней).

**AI usage:** при формировании промпта для Research Agent или Sales Coach — выбираются файлы по матчингу тегов карточки. Подмешиваются в системный промпт.

### 6.10 WebForm Builder

**6 табов:** 🎨 Дизайн · 📥 Маршрутизация · 🎯 UTM · 📊 Стили · 🔗 Embed · 📈 Аналитика

**3-column UI:**
- Палитра 16 типов полей (Имя/Email/Телефон/Telegram/Компания/ИНН/Сегмент/Город/Кол-во точек/Сообщение/Файл/Дата/Чекбокс/UTM/Источник/Cookie ID)
- Live-preview формы (drag-drop полей, click → выбор)
- Field config panel (label, placeholder, обязательное, валидация, mapping на лид, AI после-сабмита, статистика 30 дней, embed-код)

**AI после сабмита:**
1. Quality pre-filter (отсеять spam) → reject early
2. Дедупликация по email/ИНН
3. Research Agent enrichment → AI Brief
4. Auto-assign по сегменту через `app/assignment/`

### 6.11 Notifications

**UI:** 🔔 bell в top-right с unread count + drawer справа

**Drawer:**
- Filter chips (Все / 🔥 Срочные / 🤖 AI / 💬 Сообщения / ⏸ Системные)
- Группировка по времени (Сейчас / Сегодня / Вчера / Ранее)
- Item: иконка по типу + заголовок + desc + время + action кнопки + unread индикатор
- Mark all read · Settings

**Каналы доставки:**

| Канал | Назначение |
|---|---|
| In-app | bell + drawer (всегда вкл) |
| Email | для дайджестов и важных событий |
| Push (web/desktop) | срочные, тихие часы |
| Telegram bot | срочные / новые сообщения / push-fallback |
| SMS | только критичное (биллинг limit) |

**Матрица событий × каналов** (в Settings → Notifications): 10 типов событий × 5 каналов с галочками.

**AI-сглаживание:** похожие события в окне 2-5 мин сворачиваются («5 карточек обогащено», «3 сообщения от Эрнесто»).

**Тихие часы:** 22:00-08:00 default — push/Telegram off.

**Email digest:** утренний brief 8:00 + weekly report пятница 18:00.

### 6.12 Onboarding (4 шага, fullscreen)

1. **Welcome / Google OAuth** — кнопка «Войти через Google» + invite-link + privacy
2. **Профиль** — имя/email из Google · 3 роли (Junior/Middle-Senior/Head) · спецификация чипами (HoReCa/Ритейл/QSR/АЗС/Офис/Партнёры) · **визуальный schedule grid** Пн-Вс × 9-18 (work/lunch/off) · timezone · max active leads
3. **Каналы** — Email Gmail (auto-connect через OAuth) · Telegram Business · WhatsApp/VK (Phase 2)
4. **Готово** — 3 stat-карточки + 4 CTA с чего начать (Создать вручную / Фото визитки / Импорт CSV / Bitrix24-AmoCRM)

Bypass: «Подключу позже →» в шапке каждого шага. Минимум — обязательно step 2.

### 6.13 Admin Settings

| Раздел | Содержимое |
|---|---|
| 📊 Воронки и стадии | CRUD воронок · конструктор стадий (drag-drop, цвет, rot_days, probability) |
| 👥 Команда | список с ролями · invite-ссылка с TTL · реферальный токен · стратегия AI-распределения |
| 💬 Каналы | per-channel статистика (входящих/исходящих, % матчинга, unmatched) |
| 🤖 AI-провайдеры | модели с ролью (primary/fallback) · cost summary · лимиты |
| 🔧 Кастом-поля (EAV) | список + типы + условия применения (по сегменту/стадии) |
| 🔔 Уведомления | матрица + тихие часы + дайджест |
| 🔗 Интеграции/webhooks | Bitrix24, Slack, Notion, 1C, Zapier, собственный API |
| 🔐 Роли и права | базовые + кастомные с гранулярными правами |
| 📜 Audit log | все события за период с фильтрами |
| 💳 Тариф / 📈 Использование AI | биллинг + графики |

### 6.14 Lead creation flows

**4 способа создать лид:**

#### A. Quick add (default)

Modal с полями: Компания* (или ИНН) · Сайт · Воронка · Стадия · Ответственный («🤖 AI распределит»). Submit → новая карточка в «Новые лиды» с pulsing **⏳ AI** badge → AI Research Agent в фоне → через ~10 сек заполненная карточка.

#### B. Полная форма

Все поля: + ФИО контакта, должность, email, телефон, сумма сделки, источник, теги, заметка.

#### C. Фото визитки (📷 mode)

Drag-drop фото визитки → AI parsing pipeline:
- ✓ OCR текст → ✓ AI парсит поля → ✓ СБИС поиск → ⏳ Research Agent
- Извлечение: ФИО, должность, компания+ИНН, email, телефон, Telegram

#### D. Bulk update от внешнего AI (новое)

3-step workflow в Import-модалке (`Pipeline → 📥 Импорт`):

1. **Скачать снэпшот** — `leads_snapshot.yaml` со всеми текущими лидами + AI Brief
2. **Скопировать промпт** — готовый промпт со схемой ответа
3. **Загрузить ответ** → preview diff → Apply

**DrinkX Update Format v1.0:**

```yaml
format: drinkx-crm-update
version: 1.0
generated_at: 2026-05-03T15:00:00Z
generator: <имя AI>

updates:
  - action: update | create | skip
    match_by: inn | company_name | id | email
    company:
      name: ...
      inn: ...
    fields:
      ai_data:
        company_profile: "..."        # перезаписать
        growth_signals:
          add: [...]                  # дополнить
          remove: [...]
        fit_score: 9                  # перезаписать
      contacts:
        add: [...]
        update_by_email:
          "x@y.ru": {...}
      tags:
        add: [...]
        remove: [...]
      next_steps:
        replace: [...]
      stage: "Переговоры"
      assigned_to: "elena@drinkx.ru"
```

**Preview UI:** ✨ создать (12) · 🔄 обновить (28) · ⏸ skip дубль (5) · ⚠️ конфликт (2) с раскрытием diff.

**Также форматы:** CSV, JSON, Excel, ZIP с Markdown (Obsidian-style для drinkx-client-map совместимости), Bitrix24/AmoCRM dump.

### 6.15 Export

Простой modal: scope (текущая воронка / все / по фильтру / только won) + формат (YAML/JSON/CSV/Excel/Markdown ZIP) + поля (basic / AI Brief / messages / activities / quotes) + опция «включить промпт-задание для AI».

### 6.16 Apify Integration (новое — внешний lead-gen)

**Уровень 1: Input через bulk-update flow**

Менеджер использует Claude Desktop + Apify Custom Connector с готовым промптом → получает YAML → загружает в CRM через Bulk Update.

**Уровень 2: Apify как ещё один источник Research Agent**

В Phase 1 добавить в `app/enrichment/sources/`:
- ApifyGoogleMapsScraper — все точки сети, рейтинги, отзывы
- ApifyYandexPlacesScraper — для РФ
- Apify2GISScraper
- ApifyLinkedInScraper — ЛПР с должностями
- ApifyInstagramScraper — для HoReCa

**Уровень 3 (Phase 2): Pre-built lead-gen wizard в CRM**

Кнопка `+ Лид → 🌐 Найти через Apify` → input типа «100 кофеен Москвы с 5+ точками» → Apify scraping → AI обогащение → массовое создание лидов.

## 7. AI Architecture

### 7.1 Research Agent Pipeline

```
Lead Created / Enrichment Triggered
            │
            ▼
    Step 0: Quality pre-filter
    - regex/правила: компания не в стоп-листе, не дубль, не банкрот
    - mini-LLM (~50 токенов): «релевантный B2B-лид? yes/no/maybe»
    - Только yes/maybe → Step 1
            │
            ▼
    Step 1: Query Builder (LLM)
    - 4-6 поисковых запросов на основе company_name + city + industry_hint
            │
            ▼
    Step 2: Parallel Fetch (asyncio.gather, 15s timeout each)
    ├── BraveSearch.search(Q1...QN) → chunks[]
    ├── HH_API.search(company) → vacancies[]
    ├── web_fetch(company_website) → text
    ├── ApifyGoogleMaps.search(company) → locations  [Phase 1]
    ├── ApifyLinkedIn.search(company) → contacts     [Phase 1]
    └── (другие источники)
    + 24h Redis cache по company_name (40-60% hits при дублях)
            │
            ▼
    Step 3: Relevance Filter
    - Отфильтровать шум, омонимы (другие компании похожих названий)
    - Max total context: 8000 tokens
            │
            ▼
    Step 4: Synthesis LLM
    - System: «Ты старший менеджер DrinkX (B2B умные кофе-станции)»
    - Knowledge Base injection (matching tagов карточки)
    - business-profile config (`config/drinkx_profile.yaml`)
    - JSON-output schema с fallback-defaults (Pydantic Optional everywhere)
            │
            ▼
    Сохранить в lead.ai_data + enrichment_runs (cost, duration, sources_used)
    WebSocket event → UI панель обновляется
```

### 7.2 Output Schema (с fallback-defaults — Krayin pattern)

```python
class ResearchOutput(BaseModel):
    company_profile: str = "Информация недоступна"
    scale_signals: str = ""
    growth_signals: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    decision_maker_hints: str = ""
    drinkx_fit_score: int = Field(ge=0, le=10, default=5)
    next_steps: list[NextStep] = Field(default_factory=list)
    urgency: Literal["low", "medium", "high"] = "low"
    sources_used: list[str] = Field(default_factory=list)
```

Никогда не падать при отсутствии полей в LLM-ответе.

### 7.3 drinkx_fit_score логика

| Сигнал | Вес | Примеры |
|---|---|---|
| Кол-во точек / офисов | +высокий | «сеть 50 кофеен», «8 офисов в РФ» |
| Вакансии office-manager / HR | +средний | офис-инфраструктура растёт |
| Упоминание кофе/кейтеринга/HoReCa | +средний | уже думают |
| Рост (новые точки, раунд) | +высокий | деньги, растут |
| Судебные иски, долги (СБИС) | −высокий | риск неоплаты |
| Ликвидация | −критично | блокировать сделку |
| ЛПР сменился недавно | +средний | новый человек = новые решения |

### 7.4 Knowledge Base (`knowledge/drinkx/*.md`) для grounding

Папка с playbooks подмешивается в системный промпт Research Agent и Sales Coach. Файлы:
- `playbook_horeca.md`, `playbook_retail.md`, `playbook_azs.md`, `playbook_qsr.md`, `playbook_office.md`, `playbook_franchise.md`
- `objections.md`, `success_stories.md`, `competitors.md`, `product_specs.md`

Загружается при старте сервиса в Redis. Менеджер редактирует через админку (UI описан в §6.9).

### 7.5 business-profile config

`config/drinkx_profile.yaml` подмешивается в КАЖДЫЙ AI-промпт:

```yaml
company:
  name: DrinkX
  product: умные кофе-станции для B2B (офис, HoReCa, ритейл, АЗС)
  unique_value:
    - автоматизация без бариста
    - стабильное качество
    - снижение себестоимости чашки
icp:
  ideal_segments: [horeca_chains, retail_grocery, qsr, gas_stations]
  ideal_size: 10+ точек
  ideal_pain: [нехватка бариста, текучка, нестабильное качество]
voice_tone: профессиональный, без воды, с цифрами
language: ru
```

### 7.6 Model tier switching (cost control)

| Use case | Default model | Fallback |
|---|---|---|
| Bulk Research Agent | DeepSeek V3 | OpenAI GPT-4o-mini |
| High-fit карточки (fit ≥ 8) — re-enrichment | OpenAI GPT-4o | Gemini 1.5 Pro |
| Sales Coach chat | DeepSeek V3 | — |
| Daily Plan generation | DeepSeek V3 | OpenAI GPT-4o-mini |
| Visit-card OCR + parsing | OpenAI GPT-4o (vision) | Gemini 1.5 Pro |

### 7.7 LLM Provider Abstraction

```python
class AIProvider(Protocol):
    async def complete(self, prompt: str, system: str = "",
                       max_tokens: int = 1000) -> str: ...

class DeepSeekProvider: ...
class OpenAIProvider: ...
class GeminiProvider: ...
class OllamaProvider: ...    # self-hosted, Phase 2

def get_ai_provider() -> AIProvider:
    backend = os.getenv("CRM_AI_BACKEND", "deepseek")
    return {"deepseek": DeepSeekProvider, "openai": OpenAIProvider,
            "gemini": GeminiProvider, "ollama": OllamaProvider}[backend]()
```

### 7.8 Rate Limiting & Cost Control

| Параметр | Значение | Обоснование |
|---|---|---|
| Max обогащений/день/карточку | 1 | данные не меняются быстрее |
| Max параллельных Research Agent jobs | 5 | не перегружать API rate limit |
| Timeout на источник | 15s | fail gracefully |
| Max context Synthesis LLM | 8000 tokens | ~$0.002/карточку DeepSeek |
| Приоритет очереди | Новые > Активные стадии > Refresh | FIFO внутри приоритета |
| Fallback при ошибке источника | пропустить, продолжить с остальными | partial > nothing |
| Повтор при полной ошибке | 3 попытки, backoff 1h/2h/4h | |

**Стоимость на DrinkX масштабе (500 карточек × 1 обогащение/день):**
- Brave Search API: ~$3/1000 → 2500/день → $7.50/день → нужен cache
- DeepSeek V3 synthesis: ~500 × $0.0003 = $0.15/день
- HH API: бесплатно
- Apify: ~$5-10/мес
- **Итого AI: ~$50-70/мес**

## 8. Technical Architecture

### 8.1 Stack

**Frontend:**
- Next.js 15 (App Router)
- shadcn/ui + Tailwind CSS
- Zustand + React Query (TanStack)
- WebSocket для real-time enrichment progress + notifications
- NextAuth.js + Google OAuth

**Backend:**
- Python 3.12 + FastAPI (async)
- SQLAlchemy 2.0 async
- Celery + Redis для очередей
- Pydantic v2 для schemas
- Alembic для миграций

**Cloud:**
- PostgreSQL: Supabase (managed, backups, RLS)
- Redis: Upstash (serverless, pay-per-use)
- Logs: Railway built-in → Sentry для errors
- Frontend hosting: Vercel
- Backend + Workers: Railway (или Fly.io)

**AI:**
- DeepSeek V3 primary
- OpenAI GPT-4o (vision, high-value)
- Gemini 1.5 Pro (fallback)
- Brave Search API (web)
- HH.ru Public API (бесплатно)
- Apify (Phase 1.5)
- NO local Ollama в v1.0 (Phase 2)

### 8.2 Backend Modular Structure (Krayin-inspired)

**Package-per-domain, НЕ layered:**

```
backend/
  app/
    leads/           # CRUD, поиск, фильтры
    pipelines/       # воронки, стадии, переходы
    contacts/        # ЛПР CRUD
    inbox/           # email + telegram, матчинг → лид
    enrichment/      # Research Agent, источники, кэш
      sources/       # brave.py, hh.py, apify_*.py, web_fetch.py
    automation/      # workflow rules, триггеры, stage_change hooks
    assignment/      # workload distribution с pluggable стратегиями
    activity/        # unified activity stream
    followups/       # follow-up sequences, reminders
    quote/           # КП builder
    template/        # email/sms/tg шаблоны
    auth/            # OAuth, JWT, roles, workspaces, onboarding
    forms/           # WebForms — public submit + admin CRUD
    knowledge/       # KB CRUD + AI grounding selector + usage tracking
    notifications/   # dispatcher с channels (inapp/email/push/tg/sms) + aggregator
    import_export/   # parsers (yaml/csv/xlsx/bitrix/amocrm/markdown_zip), differ, applier
    scheduled/       # Celery beat jobs registry
    common/          # shared models, utils
```

Каждый пакет: `models.py`, `schemas.py`, `repositories.py`, `services.py`, `tasks.py` (Celery), `routers.py`, `events.py`.

### 8.3 Data Model

```sql
-- Workspace (компания-клиент)
workspaces: id, name, domain, plan, settings_json, created_at

-- Users (менеджеры)
users: id, workspace_id, email, name, role,
       working_hours_json, max_active_deals, google_id,
       onboarding_completed, created_at

-- Pipelines (воронки)
pipelines: id, workspace_id, name, type (sales|partner|service),
           is_default, created_at

-- Stages (стадии воронки) — данные, не enum
stages: id, pipeline_id, name, position, color,
        rot_days, probability, is_won, is_lost

-- Leads (карточки лидов)
leads: id, workspace_id, pipeline_id, stage_id, assigned_user_id,
       company_name, segment, tier, priority,
       email, phone, website, inn,
       deal_amount, source, tags_json,
       ai_data JSON,           -- результат обогащения
       last_enriched_at,
       next_action_at,
       is_archived, is_rotting,
       created_at, updated_at

-- Contacts (ЛПР, унифицированная сущность)
contacts: id, lead_id, name, title, role,
          email, phone, telegram, linkedin_url,
          source, confidence, verified_status (verified|to_verify),
          created_at, updated_at

-- Custom Attributes (EAV из Krayin)
custom_attributes: id, workspace_id, entity_type (lead|contact),
                   key, label, type (text|number|select|date|multiselect),
                   options_json, required, position, applies_to_segments
custom_attribute_values: id, entity_id, attribute_id,
                         value_text, value_number, value_date

-- Activity stream (EspoCRM Stream pattern)
activities: id, workspace_id, lead_id, user_id,
            type (comment|task|reminder|file|email|tg|wa|system|enrichment|stage_change|...),
            payload_json,
            -- task fields
            task_title, task_due_at, task_assignee_id, task_done, task_completed_at,
            -- reminder fields
            reminder_title, reminder_trigger_at, reminder_kind (manager|auto_email|ai_hint),
            reminder_status,
            -- file fields
            file_url, file_name, file_size, file_kind (kp|presentation|contract|photo|other),
            -- email/tg/wa
            channel, direction (inbound|outbound),
            from_identifier, to_identifier,
            subject, body, raw_payload_json,
            created_at

-- Follow-up stages per lead
followups: id, lead_id, name, due_at, status (pending|active|done|overdue),
           reminder_kind (manager|auto_email|ai_hint), reminder_template_id,
           notes, position, completed_at, created_at

-- Quote / КП
quotes: id, lead_id, workspace_id, number, status (draft|sent|accepted|rejected),
        recipient_contact_id, valid_until,
        subtotal, discount, total, sent_at, accepted_at, created_at
quote_lines: id, quote_id, position, product_name, product_id_ref,
             quantity, unit_price, discount, total, description

-- Templates
templates: id, workspace_id, channel (email|tg|sms),
           name, subject, body, variables_json, is_archived

-- Materialized AI runs
enrichment_runs: id, lead_id, workspace_id, status (pending|running|done|failed),
                 sources_json,         -- какие источники + их статусы
                 input_json, output_json,
                 cost_tokens, cost_usd, duration_ms,
                 model, attempt,
                 created_at, completed_at, error_text

-- Daily plans
daily_plans: id, user_id, workspace_id, date, plan_json, generated_at

-- Channel connections
channel_connections: id, workspace_id, user_id (optional, persornal vs team),
                     channel_type (email|telegram|whatsapp|smtp),
                     credentials_encrypted_json,
                     status (active|error|disconnected),
                     last_sync_at, created_at

-- WebForms
web_forms: id, workspace_id, name, slug, fields_json, target_pipeline_id,
           target_stage_id, redirect_url, is_active, submissions_count
form_submissions: id, web_form_id, lead_id, raw_payload, utm_json, ip, created_at

-- Knowledge Base
knowledge_files: id, workspace_id, category, name, content_md,
                 tags_json, usage_count, last_used_at, created_by, updated_at
knowledge_versions: id, file_id, content_md, author_id, created_at

-- Notifications
notifications: id, user_id, type, payload_json,
               read_at, dispatched_via_json, created_at
notification_preferences: id, user_id, event_type, channels_json,
                          quiet_hours_start, quiet_hours_end

-- Import/Export jobs
import_jobs: id, workspace_id, source (file|bulk_update|api),
             format, status (uploaded|previewed|applied|failed),
             total, created, updated, skipped, conflicts,
             diff_json, applied_changes_json,
             initiated_by, applied_by, created_at, applied_at
```

### 8.4 Materialized job records pattern (EspoCRM)

Все long-running задачи (enrichment, daily plan, mass email, import) — **сущности в БД**, не только Celery tasks. Даёт:
- Аудит: кто, когда, сколько потратил
- Retry: можно перезапустить failed jobs из админки
- Биллинг: суммируем `cost_usd` за период
- Debugging: видим input/output каждого AI-запуска

### 8.5 Deployment Architecture

```
Browser (https://crm.drinkx.ru)
   │
   ▼
Vercel (Next.js frontend)
   │  REST API + WebSocket
   ▼
Railway: FastAPI Backend
   ├── REST: /leads, /pipelines, /contacts, /activities, ...
   ├── WS: /ws/{user_id} → push enrichment progress + notifications
   │
   ├── Railway: Celery Worker  ← Upstash Redis Queue
   │     ├── ResearchAgent.run(lead_id)
   │     │     ├── asyncio.gather(BraveSearch × N + HH + Apify + web_fetch)
   │     │     └── Synthesis LLM с KB injection
   │     ├── DailyPlanGenerator.run(user_id)  [cron 08:00 TZ]
   │     ├── FollowupReminderDispatcher.run() [cron каждые 15 мин]
   │     ├── NotificationAggregator.run()     [cron каждые 5 мин]
   │     └── BulkImporter.apply(import_job_id)
   │
   └── Supabase PostgreSQL (managed + RLS)
```

### 8.6 Стоимость инфраструктуры (DrinkX масштаб)

| Сервис | Plan | $/мес |
|---|---|---|
| Vercel | Pro | $20 |
| Railway (API + 2 workers) | Pro | $30 |
| Supabase Postgres | Pro | $25 |
| Upstash Redis | Pay-per-use | $5-15 |
| Brave Search API | Pay-per-use | $5-15 |
| DeepSeek V3 API | Pay-per-use | $5-15 |
| OpenAI (high-value cards) | Pay-per-use | $5-20 |
| Apify scrapers | Pay-per-use | $5-15 |
| HH.ru API | Free | $0 |
| Sentry | Team | $26 |
| **Итого** | | **~$130-180/мес** |

## 9. Anti-patterns — чего НЕ делать

1. **Не делать sync REST для длинных AI-задач** — минимум 30 сек → POST создаёт `enrichment_run`, возвращает ID; SSE/WebSocket стрим прогресса; Celery воркер пишет результат
2. **Не давать LLM прямой SQL access без whitelisting** — даже read-only к raw таблицам = риск SQL injection через prompt + утечка PII в логи провайдера. Только узкие, предопределённые view/функции.
3. **Не делать multi-agent ради multi-agent** — один оркестратор + явные Celery шаги. Multi-agent только когда есть реальная независимость задач.
4. **Не делать AI auto-actions без human-in-the-loop** — для B2B критично: AI ПРЕДЛАГАЕТ, менеджер аппрувит. Никаких автоматических исходящих сообщений без явного согласия.
5. **Не делать metadata-driven «всё через DSL»** — соблазнительно, но даёт нечитаемый код. Metadata только для полей/форм/навигации.
6. **Не делать монолитный `cron/` со скриптами** — все периодические задачи через Celery beat с явным реестром в `app/scheduled/jobs.py`.
7. **Не игнорировать output schema fallback'и** — каждое поле ResearchOutput имеет default. LLM никогда не валит pydantic.

## 10. Phasing & Roadmap

### Phase 0 — UX/UI Design (✅ ЗАВЕРШЕНО)

- [x] Кликабельный HTML-прототип с реальной базой 131 клиента
- [x] 11+ экранов · 7+ модалок · 3 drawer'а
- [x] taste-soft hi-fi версия для тестирования
- [x] PRD v1.3 + additions v1.4 → v2.0 (этот документ)
- [x] Тестирование с менеджерами DrinkX

### Phase 1 — MVP (1.5-2 месяца)

**Sprint 1 (1 неделя): Foundation**
- [ ] Next.js 15 app (App Router, shadcn/ui, Zustand, React Query)
- [ ] FastAPI backend (package-per-domain структура)
- [ ] Supabase setup (Postgres + Auth + Storage + RLS)
- [ ] Upstash Redis
- [ ] DB schema migration (все сущности из §8.3)
- [ ] CI/CD: Vercel + Railway
- [ ] Sentry integration

**Sprint 2 (1 неделя): Auth + Onboarding**
- [ ] Google OAuth через Supabase Auth
- [ ] Workspace creation flow
- [ ] 4-step onboarding (welcome / profile / channels / done)
- [ ] Schedule grid editor (рабочие часы)

**Sprint 3 (2 недели): Core CRUD**
- [ ] REST endpoints: /leads, /pipelines, /stages, /contacts, /activities
- [ ] Today screen: рендерит из API
- [ ] Pipeline screen: drag-drop persisted, search, фильтры (сегмент + город)
- [ ] Lead Card: 4 таба + редактируемые ЛПР + activity feed (mock + реальные комментарии)
- [ ] Brief drawer
- [ ] Migration script: data.js → real DB (одноразово)

**Sprint 4 (2 недели): AI Enrichment**
- [ ] BraveSearch integration
- [ ] HH.ru API integration
- [ ] web_fetch source
- [ ] DeepSeek V3 provider + LLMProvider Protocol
- [ ] Research Agent оркестратор (Celery)
- [ ] enrichment_runs сущность с cost tracking
- [ ] WebSocket progress в карточке
- [ ] Quality pre-filter
- [ ] Knowledge Base loader (markdown в Redis)
- [ ] business-profile config injection

**Sprint 5 (1 неделя): Daily Plan + Follow-ups**
- [ ] Celery beat: cron 08:00 на workspace TZ
- [ ] AI-driven приоритизация
- [ ] Today screen: реальные задачи
- [ ] Follow-up sequences с auto-seed
- [ ] FollowupReminderDispatcher (cron 15 мин)
- [ ] Activity feed: comment / task / reminder / file (полноценный)

**Sprint 6 (1 неделя): Polish + Launch**
- [ ] Notifications: in-app + email digest
- [ ] Audit log
- [ ] Empty states + error states
- [ ] Mobile responsive
- [ ] Performance optimization
- [ ] Soft launch для DrinkX

**MVP shipped ≈ 8-9 недель**

### Phase 2 — Inbox + Advanced (1.5 месяца)

- Unified Inbox: Email IMAP/SMTP + Telegram Business webhook
- Quote/КП builder с PDF generation
- WebForm builder + public submit endpoint
- Bulk Import/Export (все форматы)
- Knowledge Base UI (CRUD)
- Apify integration как enrichment source
- Notifications: push + Telegram bot
- Multi-pipeline переключатель
- Settings: команда, каналы, AI-провайдеры, custom-fields
- WhatsApp Business (если потребуется)

### Phase 3 — Scale + Polish (1 месяц)

- MCP server поверх FastAPI (для внешних AI: Claude Desktop / Cursor)
- Public signal monitoring (cron HH.ru на pipeline-компании)
- NL search over pipeline (через whitelisted views)
- AI Sales Coach (chat sidebar в карточке)
- Visit-card OCR parser
- Vector DB для retrieval похожих кейсов
- Stalled deal detector с auto-recommendations
- Performance: virtualization для Pipeline columns при 1000+ лидах
- Apify lead-gen wizard в UI

## 11. Success Metrics

| Метрика | Baseline | Target (3 мес после launch) |
|---|---|---|
| Время менеджера на поиск инфо о лиде | ~40 мин/день | < 10 мин/день |
| % карточек с актуальными AI-данными (< 24h) | 0% | > 85% |
| Равномерность нагрузки (std dev) | N/A | < 15% отклонение |
| Конверсия лид → сделка | baseline | +15% |
| Онбординг нового менеджера | ~2 ч | < 15 мин |
| Avg время в стадии «КП отправлено» | 5.8 дня | 3 дня |
| % follow-up задач выполненных в срок | N/A | > 80% |
| AI cost / лид | N/A | < $0.20 |
| Cache hit rate (Brave + KB) | N/A | > 35% |

## 12. Open Questions

1. **MCP-server timing** — Phase 2 или v1.5?
2. **Multi-tenancy isolation** — Postgres RLS в Supabase или отдельные схемы per workspace?
3. **Vector DB на v1.0?** — Pinecone / pgvector / отложить до Phase 3?
4. **Quote/КП конфигуратор** — line items с фиксированными моделями или свободный?
5. **WebForm endpoint** — REST POST или embed-script сборка?
6. **Telegram Business** — нужен Premium-аккаунт DrinkX. Кто его подключает?
7. **Хостинг в РФ?** — Vercel/Railway могут не работать без VPN. Альтернатива: Selectel/Timeweb для бэка.

## 13. References

**Phase 0 артефакты:**
- Прототип: https://globalsasha.github.io/drinkx-crm-prototype/
- taste-soft версия: /index-soft-full.html
- Repo: https://github.com/GlobalSasha/drinkx-crm-prototype
- Design spec: `docs/superpowers/specs/2026-05-03-smart-ai-crm-phase0-ia-ux-design.md`
- PRD additions: `docs/PRD-additions-v1.4.md`

**Источники данных:**
- `Downloads/drinkx-client-map-v0.5-linkedin-industry-enriched/` — 131 клиент с обогащением
- `data/research_results_v0.3.csv`, `industry_*_v0.4.csv`, `linkedin_*_v0.5.csv`, `outreach_tiers_v0.5.csv`
- 6 segment .md файлов
- ~700 people .md (биографии ЛПР)
- 134 opportunity .md

**Open-source CRM референсы (исследовано в Phase 0):**
- EspoCRM — metadata-driven, Stream API, EmailQueueItem materialization
- Krayin — Laravel, package-per-domain, EAV attributes, AI lead generation, OpenRouter роутер
- atomic-crm — React + shadcn, DataProvider abstraction, FE-нарезка по фичам
- Relaticle / EspoCRM Copilot — MCP-сервер pattern (Phase 3)
- ai-crm-agents — FastAPI + Celery + Redis stack twin
- business-leads-ai-automation — business-profile config-as-prompt-context

**Open Design (taste-soft skill):**
- nexu-io/open-design — 61 design skill для hi-fi UI
- Применён `web-prototype-taste-soft` для индекс-soft.html и index-soft-full.html
