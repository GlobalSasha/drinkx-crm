"""External-AI prompt for the bulk-update loop (PRD §6.14).

The manager downloads `leads_snapshot.yaml` from `/api/export/snapshot`,
pastes it together with this prompt into ChatGPT / Claude / Perplexity,
and uploads the AI's response into the import wizard. The diff engine
in Group 9 takes it from there.

This is intentionally a server-side constant so we can revise the prompt
shape without a frontend deploy. The frontend fetches it via
`/api/export/bulk-update-prompt`.
"""
from __future__ import annotations


BULK_UPDATE_PROMPT: str = """## Задача
Обнови базу B2B-клиентов DrinkX на основе свежего research.

## Контекст
- DrinkX продаёт умные кофе-станции в HoReCa, ритейл, АЗС, офисы.
- К сообщению прикреплён `leads_snapshot.yaml` — текущая база лидов.
- Нужно: (a) добавить пропущенные сигналы и факты, (b) обновить
  `fit_score` если есть новые данные, (c) предложить новых лидов
  которых нет в базе.

## Формат ответа
Верни строго в формате DrinkX Update Format v1.0:

```yaml
format: drinkx-crm-update
version: "1.0"
generated_at: 2026-05-08T10:00:00Z
generator: <твоё имя — например, "Claude Sonnet 4.6">

updates:
  - action: update           # update | create | skip
    match_by: inn             # inn | company_name | id
    company:
      name: Stars Coffee
      inn: 9705131922
    fields:
      ai_data:
        growth_signals:
          add: ["открытие в Дубае Q3 2026"]
        fit_score: 9
      contacts:
        add:
          - name: Мария Иванова
            title: Procurement
            email: m@stars.ru
            source: "LinkedIn 2026-05-08"
      tags:
        add: ["expansion-2026"]
      next_steps:
        replace:
          - "Связаться с Марией по procurement"
```

## Правила
- НЕ выдумывай факты — если нет источника, не пиши.
- Каждый новый сигнал, контакт или next_step снабжай полем `source`
  с конкретной ссылкой / датой / упоминанием.
- `action` обязателен на каждом элементе `updates[]`. Всё остальное
  опционально — пропускай поля где данных нет.
- Для существующих лидов всегда указывай `match_by: inn` если ИНН есть
  в snapshot, иначе `match_by: company_name`. Для новых — `action: create`
  без `match_by`.
- Не возвращай неизменённые лиды (`action: skip`) — сократи payload.
- Кодировка UTF-8, indent 2 spaces.
"""


__all__ = ["BULK_UPDATE_PROMPT"]
