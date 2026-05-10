# Sprint 3.1 — Lead AI Agent

**Phase:** 3 (первый спринт)
**Branch:** `sprint/3.1-lead-ai-agent` (создать от main после merge Sprint 2.7)
**Status:** READY TO PLAN

---

## Цель спринта

Запустить единый AI-агент внутри карточки лида:

- **Background**: Celery-задача следит за паузами в переписке и отклонениями от методологии продаж → показывает баннер-рекомендацию
- **Foreground**: Sales Coach — чат-drawer с полным контекстом лида, открывается по кнопке

Агент работает на одном системном промпте (`lead-ai-agent-skill.md`) и всегда читает `product-foundation.md` первым.

---

## Прочитать перед стартом

- `docs/brain/00_CURRENT_STATE.md` — состояние после Sprint 2.7
- `docs/brain/01_ARCHITECTURE.md` §5 — AI Modules
- `docs/skills/lead-ai-agent-skill.md` — поведенческая спецификация агента
- `docs/knowledge/agent/product-foundation.md` — фундаментный продуктовый контекст
- `app/enrichment/` — паттерн LLMProvider (ADR-018), переиспользовать
- `app/knowledge/` — паттерн загрузки KB-файлов, переиспользовать

---

## Scope

### Phase A — Knowledge files в репо (~15 мин)

Скопировать в репо:
- `docs/skills/lead-ai-agent-skill.md` ← из артефакта
- `docs/knowledge/agent/product-foundation.md` ← из артефакта

Эти файлы читаются из файловой системы при сборке системного промпта. Не в БД, не в Redis.

> **NOTE:** Артефакты ещё не предоставлены — запросить у пользователя перед стартом Phase A.

---

### Phase B — Migration (~30 мин)

**Migration 0023 (НЕ 0013):** добавить поле `agent_state` в таблицу `leads`.

> **ВНИМАНИЕ:** Исходная спека предполагала migration 0013, но 0013 уже занят (`0013_default_pipeline`). К моменту старта Sprint 3.1 будут заняты также 0021 (automation_steps) и 0022 (lead_tg_chat_id) от Sprint 2.7. Поэтому фактический индекс — 0023 или больше; уточнить на момент старта.

```sql
ALTER TABLE leads ADD COLUMN agent_state JSONB NOT NULL DEFAULT '{}';
```

Схема `agent_state` (Pydantic-модель):

```python
class AgentState(BaseModel):
    spin_phase: str | None = None          # "Situation" | "Problem" | "Implication" | "Need-payoff"
    spin_notes: str | None = None
    missing_contacts: list[str] = []       # ["economic_buyer", "champion"]
    gate_blockers: list[str] = []
    suggestions_log: list[SuggestionLog] = []
    silence_alert_sent_at: datetime | None = None
    last_analyzed_activity_id: str | None = None
    coach_session_count: int = 0

class SuggestionLog(BaseModel):
    date: str
    trigger: str       # "silence_3d" | "silence_7d" | "spin_gap" | "rotting" | "stage_changed" | "new_inbound"
    text: str
    manager_action: str = "pending"  # "pending" | "accepted" | "ignored"
```

---

### Phase C — Backend package `app/lead_agent/` (~2–3 дня)

Структура пакета (паттерн package-per-domain, ADR-009):

```
app/lead_agent/
  __init__.py
  schemas.py       — AgentState, AgentSuggestion, ChatMessage, ChatRequest
  context.py       — LeadAgentContext: собирает полный контекст для одного лида
  prompts.py       — строит system prompt из knowledge-файлов
  runner.py        — вызывает LLM, парсит ответ в AgentSuggestion
  tasks.py         — Celery задачи
  routers.py       — REST endpoints
```

#### `context.py` — LeadAgentContext

Собирает за один вызов:

```python
@dataclass
class LeadAgentContext:
    lead: Lead                    # stage, priority, deal_type, segment, days_in_stage, is_rotting
    contacts: list[Contact]       # с ролями (economic_buyer / champion / etc.)
    activities: list[Activity]    # последние 20, order by created_at DESC
    ai_data: dict                 # lead.ai_data (AI Brief)
    gate_status: dict             # выполнено / не выполнено для следующей стадии
    agent_state: AgentState       # текущая память агента
    kb_excerpts: list[str]        # playbook по сегменту лида (из app/knowledge/)
    silence_days: int             # дней без исходящих активностей
    silence_total_days: int       # дней без любых активностей
```

Все данные получаются через существующие репозитории (leads, contacts, activities). Нет новых DB-запросов вне существующих паттернов.

#### `prompts.py` — сборка system prompt

```python
def build_system_prompt(context: LeadAgentContext, mode: str) -> str:
    """
    mode: "background" | "coach"
    
    Структура промпта:
    1. product-foundation.md  (читается из файла, кешируется в памяти процесса)
    2. Секции из lead-ai-agent-skill.md релевантные для mode
    3. Контекст лида (сериализованный LeadAgentContext)
    """
```

Файлы читаются один раз при старте воркера, кешируются в `_FOUNDATION_CACHE` и `_SKILL_CACHE`. Не читать с диска при каждом запросе.

#### `runner.py` — LLM-вызов

```python
class AgentRunner:
    async def get_suggestion(self, context: LeadAgentContext) -> AgentSuggestion:
        """Background mode: анализ → одна рекомендация или None"""
    
    async def chat(self, context: LeadAgentContext, history: list[ChatMessage], message: str) -> str:
        """Foreground mode: ответ на сообщение менеджера"""
```

- `get_suggestion` → `mimo-v2-flash` (дёшево, часто)
- `chat` → `mimo-v2-pro` (качество важнее)
- Fallback chain через существующий `get_llm_provider()` (ADR-018)

`AgentSuggestion` — структурированный ответ:

```python
class AgentSuggestion(BaseModel):
    trigger: str             # причина: "silence_3d" | "spin_gap" | "no_economic_buyer" | ...
    icon: str                # эмодзи для баннера: "⏰" | "⚠️" | "👤" | "📋"
    title: str               # короткий заголовок (до 60 символов)
    body: str                # 1–2 предложения объяснения
    actions: list[AgentAction]  # кнопки (1–2 максимум)
    silent: bool = False     # True = ничего не показывать

class AgentAction(BaseModel):
    label: str               # текст кнопки
    intent: str              # "draft_message" | "open_coach" | "fill_gate" | "open_contacts"
    payload: dict = {}       # параметры для intent
```

LLM возвращает JSON. Промпт требует строго JSON-ответ без markdown-обёртки. Парсинг с fallback на `silent=True` при невалидном JSON.

#### `tasks.py` — Celery

```python
@celery_app.task(name="lead_agent.background_check")
async def lead_agent_background_check(lead_id: str):
    """
    1. Собрать LeadAgentContext
    2. Проверить: не было ли уже уведомления за последние 24ч (Redis key: agent_notif:{lead_id})
    3. Вызвать runner.get_suggestion()
    4. Если suggestion.silent = False → сохранить в agent_state.suggestions_log
    5. WebSocket push → обновить баннер в UI
    """

@celery_app.task(name="lead_agent.scan_silence")
async def scan_silence_leads():
    """
    Запускается каждые 6 часов.
    Находит активные лиды где последняя исходящая активность > 3 дней.
    Для каждого запускает lead_agent_background_check(lead_id).
    """
```

Beat schedule — добавить в `app/scheduled/jobs.py`:

```python
{"name": "lead_agent_scan", "task": "lead_agent.scan_silence", "schedule": crontab(minute=0, hour="*/6")}
```

Rate limit (Redis): `agent_notif:{lead_id}` с TTL 24h. Если ключ существует — не запускать background check.

Trigger `new_inbound` — из `app/inbox/` при получении нового сообщения: через 15 минут запустить `lead_agent_background_check.apply_async(args=[lead_id], countdown=900)`.

Trigger `stage_changed` — из `app/automation/stage_change.py`: сразу после успешного перехода стадии запустить `lead_agent_background_check.apply_async(args=[lead_id])`.

#### `routers.py` — API

```
GET  /leads/{id}/agent-suggestion      → AgentSuggestion (текущий баннер)
POST /leads/{id}/agent-chat            → ChatResponse (ответ Sales Coach)
PATCH /leads/{id}/agent-suggestion/{suggestion_id}/action   → обновить manager_action в suggestions_log
```

`GET /agent-suggestion`:
- Читает последний suggestion из `lead.agent_state.suggestions_log` где `manager_action = "pending"`
- Если нет — возвращает `{"silent": true}`
- Не генерирует на лету — только читает сохранённое

`POST /agent-chat`:

```python
class ChatRequest(BaseModel):
    messages: list[ChatMessage]   # полная история
    lead_id: str
```

Собирает контекст → вызывает `runner.chat()` → возвращает ответ. Инкрементирует `coach_session_count` в `agent_state`.

---

### Phase D — Frontend (~1 день)

#### Баннер на Lead Card

Место: между хедером карточки и табами. Показывается только когда `suggestion.silent = false`.

```
┌─────────────────────────────────────────────────────┐
│ {icon} {title}                          [×] скрыть  │
│ {body}                                              │
│ [{action[0].label}]  [{action[1].label}]            │
└─────────────────────────────────────────────────────┘
```

Компонент: `apps/web/components/lead/AgentBanner.tsx`
- `GET /leads/{id}/agent-suggestion` при открытии карточки
- Кнопка × → `PATCH .../action` с `manager_action: "ignored"`
- Кнопка action → dispatch по `intent`: `draft_message` открывает composer, `open_coach` открывает drawer, `fill_gate` → gate modal

#### Sales Coach Drawer

FAB-кнопка в правом нижнем углу карточки лида.

Компонент: `apps/web/components/lead/SalesCoachDrawer.tsx`
- Открывается по кнопке «🤖 AI Coach»
- Приветственное сообщение генерируется сразу при открытии (POST /agent-chat с пустой историей)
- Quick chips: «Что делать дальше», «Напиши follow-up», «Разбери возражение», «Проверь готовность к переходу»
- История сообщений в state компонента (не персистится — достаточно для сессии)
- Инкремент `coach_session_count` через PATCH

---

### Phase E — Интеграция с существующими триггерами (~2–3 ч)

Два хука в существующем коде (минимальные правки):

1. **`app/automation/stage_change.py`** — добавить в конец успешного перехода:

```python
lead_agent_background_check.apply_async(args=[str(lead.id)])
```

2. **`app/inbox/`** — в обработчике нового входящего сообщения:

```python
lead_agent_background_check.apply_async(args=[str(lead.id)], countdown=900)
```

---

## NOT в этом спринте

- Streaming ответов в чате (можно добавить в 3.2)
- Persist история чата в БД
- Оценка качества рекомендаций менеджером (thumbs up/down)
- SPIN-анализ входящих писем через LLM (только по паттернам пока)
- Telegram-уведомления о рекомендациях

---

## Порядок работы

```
Phase A  →  Phase B (migration NNNN)  →  Phase C (backend)
→  smoke test backend via curl  →  Phase D (frontend)
→  Phase E (hooks)  →  integration test  →  стоп, запросить deploy
```

## Как проверить вручную

1. Открыть карточку лида где последняя активность > 3 дней
2. Запустить вручную: `POST /leads/{id}/agent-suggestion/refresh` (или через Celery: `celery call lead_agent.background_check --args='["<lead_id>"]'`)
3. Перезагрузить карточку → должен появиться баннер
4. Нажать кнопку действия → проверить что intent отрабатывает
5. Открыть Sales Coach → написать «что делать дальше» → получить ответ с учётом стадии и AI Brief
6. Закрыть Sales Coach → проверить что `coach_session_count` увеличился в `lead.agent_state`

## Риски

| Риск | Вероятность | Митигация |
|---|---|---|
| LLM не возвращает валидный JSON | Средняя | Fallback на `silent=True`, не крашить |
| Слишком много Celery задач при 200+ активных лидах | Низкая | Rate limit Redis + не запускать если уже было за 24ч |
| Большой контекст → дорогой запрос | Средняя | activities ограничить 20, KB excerpts ограничить 3 блоками |
| stage_changed хук ломает stage transition | Низкая | Запускать через `.apply_async()`, не в синхронном вызове |
| Migration index conflict (исходно 0013) | Высокая | Использовать следующий свободный (0023+ после Sprint 2.7) |
