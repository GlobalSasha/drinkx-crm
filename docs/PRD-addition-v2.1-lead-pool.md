# PRD Addition v2.1 — Lead Pool & Weekly Sprint System

**Добавляет:** раздел 6.15 в PRD v2.0  
**Дата:** 2026-05-05  
**Статус:** зафиксировано, готово к разработке

---

## 6.15 Lead Pool & Weekly Sprint System

### Концепция

Общая база лидов — это **пул**. Менеджеры не владеют базой целиком.  
Они берут карточки в работу порциями (**спринт на неделю**) через автогенерацию или вручную.  
Занятые карточки недоступны другим менеджерам до момента явной передачи.

---

### 6.15.1 Модель данных

```sql
-- Добавить к таблице leads:

assignment_status  ENUM('pool', 'assigned', 'transferred')  DEFAULT 'pool'
assigned_to        UUID REFERENCES users(id)                 NULLABLE
assigned_at        TIMESTAMPTZ                               NULLABLE
transferred_from   UUID REFERENCES users(id)                 NULLABLE
transferred_at     TIMESTAMPTZ                               NULLABLE
```

**Переходы статусов:**
```
pool
 └─→ assigned   (менеджер взял: автоспринт или вручную)
       └─→ transferred  (передан другому)
             └─→ assigned  (у нового менеджера)
```

**Настройка admin (Settings → Команда):**
```
workspace.sprint_capacity_per_week: int = 20
```
Редактирует только роль `admin`. Применяется ко всем менеджерам workspace.

---

### 6.15.2 First Login Behavior

При первой авторизации менеджера:

- Pipeline пустой
- Центральный **empty state**: иконка + заголовок «Начните с плана на неделю» + кнопка **«Сформировать план»**
- В сайдбаре доступен раздел **«База лидов»** — таблица всех карточек со статусом `pool`
- Карточки со статусом `assigned` (взятые другими менеджерами) — **не отображаются** в пуле

При повторных входах (pipeline не пустой):
- Кнопка **«Сформировать план на неделю»** — в header Pipeline, рядом с `+ Лид`

---

### 6.15.3 Weekly Sprint Generator

**Точка входа:** кнопка **«Сформировать план на неделю»** в header Pipeline.

**UX Flow:**

```
Клик на кнопку
  ↓
Модальное окно «Новый спринт»
  ├── Выбор города (multi-select dropdown, список городов из пула)
  ├── [опционально] Выбор сегмента (ритейл / HoReCa / QSR / АЗС / офис / ...)
  ├── Preview: «Найдено X карточек → добавится N»
  │     где N = min(X, sprint_capacity_per_week)
  └── Кнопка «Сформировать»
        ↓
        Система выбирает N карточек из пула
        Приоритет выборки: fit_score DESC → tier ASC → created_at ASC
        Статус: pool → assigned (этому менеджеру)
        Карточки появляются в Pipeline, стадия «Новые лиды»
        Toast: «Добавлено N карточек в ваш спринт»
```

**Защита от race condition:**
```sql
UPDATE leads
SET assigned_to = :user_id, assigned_at = NOW(), assignment_status = 'assigned'
WHERE id = :lead_id AND assignment_status = 'pool'
```
Если `WHERE` не нашёл строку (другой менеджер успел раньше) → карточка пропускается, берётся следующая из очереди. Менеджер об этом не уведомляется — просто получает следующую доступную.

**Поведение в конце недели:**
- Карточки спринта остаются в pipeline, никуда не сбрасываются
- Менеджер сам решает: сформировать новый спринт (добавить ещё N карточек) или продолжать работу по текущим
- Нет автоматического сброса или архивирования по истечении недели

---

### 6.15.4 База лидов (раздел в сайдбаре)

**Новый пункт в сайдбаре:** `📋 База лидов` (видят все роли)

**UI:**
- Таблица: Компания · Город · Сегмент · Tier · Fit Score · Статус
- Фильтры: Город / Сегмент / Tier / Fit Score (min) / Статус (только pool по умолчанию)
- Поиск по названию компании
- На каждой строке: кнопка **«Взять в работу»**

**Действие «Взять в работу»:**
- Optimistic UI: строка немедленно серея («Взято»)
- `pool → assigned` (этому менеджеру) через тот же optimistic lock
- Карточка появляется в Pipeline, стадия «Новые лиды»
- Если race condition — toast: «Эту карточку только что взял другой менеджер»

**Видимость карточек в таблице:**
- Менеджер видит только `assignment_status = 'pool'`
- Admin и Head видят все карточки с колонкой «Ответственный»

---

### 6.15.5 Transfer Between Managers

**Точка входа:** Lead Card → меню действий (⋯) → **«Передать менеджеру»**

**UX Flow:**

```
Клик «Передать менеджеру»
  ↓
Модальное окно «Передача карточки»
  ├── Dropdown: выбор менеджера из активных пользователей workspace
  ├── [опционально] Комментарий к передаче
  └── Кнопка «Передать»
        ↓
        assigned_to = новый менеджер
        transferred_from = текущий менеджер
        transferred_at = NOW()
        assignment_status = 'transferred' → 'assigned'
        
        У текущего: карточка исчезает из Pipeline
        У нового: карточка появляется в Pipeline, стадия «Новые лиды»
        В Activity Feed: «Передан: [Имя] → [Имя], 05.05.2026»
        Notification новому менеджеру: «[Имя] передал вам карточку [Компания]»
```

---

### 6.15.6 Admin Settings — изменения

Добавить в раздел **Settings → Команда:**

| Поле | Тип | Дефолт | Описание |
|---|---|---|---|
| `sprint_capacity_per_week` | integer | 20 | Кол-во карточек в автоспринте |

Редактирует только `admin`. Изменение вступает в силу при следующем нажатии «Сформировать план».

---

### 6.15.7 Затронутые модули backend

```
app/
  leads/
    models.py       + assignment_status, assigned_to, assigned_at, transferred_*
    repositories.py + get_pool(city, segment, limit), claim_lead(user_id, lead_id)
    services.py     + generate_sprint(user_id, cities, segment), transfer(from, to, lead_id)
    routers.py      + POST /leads/sprint, POST /leads/{id}/transfer, GET /leads/pool
  assignment/
    (существующий модуль) — sprint_generator использует его стратегии
  notifications/
    events.py       + lead_transferred event → dispatcher
```

**Alembic migration:** добавить 4 поля к таблице `leads`.

---

### 6.15.8 Затронутые модули frontend

```
components/
  Pipeline/
    PipelineHeader     + кнопка «Сформировать план на неделю»
    SprintModal        + новый компонент (город, сегмент, preview N, кнопка)
    PipelineEmptyState + new-manager empty state с CTA
  LeadCard/
    LeadCardMenu       + пункт «Передать менеджеру»
    TransferModal      + новый компонент (dropdown менеджеров, комментарий)

pages/
  leads-pool/          + новая страница «База лидов» (таблица + фильтры)

sidebar/
  nav.tsx              + пункт «База лидов» для всех ролей
```

---

### 6.15.9 Место в роадмапе

Реализуется в **Phase 1.2 — Core CRUD** (параллельно с базовым CRUD лидов).  
Зависит от: Supabase Auth (Phase 1.1), базовая схема БД leads/users (Phase 1.0).

```
Phase 1.2 задачи (дополнить):
  ✦ Alembic migration: assignment fields
  ✦ GET /leads/pool (с фильтрами + lock-safe)
  ✦ POST /leads/sprint (генерация спринта)
  ✦ POST /leads/{id}/claim (взять вручную)
  ✦ POST /leads/{id}/transfer
  ✦ Frontend: SprintModal + TransferModal + LeadPool page
  ✦ Activity log event: lead_transferred
  ✦ Notification: lead_transferred → новому менеджеру
```
