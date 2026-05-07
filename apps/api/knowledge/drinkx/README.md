# Knowledge Base — DrinkX

Эта директория содержит сегментные плейбуки и always-on контекстные файлы, которые загружаются в синтез-промпт Research Agent.

## Файлы

| Файл | Тип | Сегменты |
|------|-----|----------|
| `playbook_horeca.md` | сегмент | horeca, coffee_shops, restaurants, hotels |
| `playbook_retail.md` | сегмент | food_retail |
| `playbook_retail_discount.md` | сегмент | non_food_retail |
| `playbook_qsr.md` | сегмент | qsr_fast_food |
| `objections_common.md` | always_on | — (все сегменты) |
| `competitors.md` | always_on | — (все сегменты) |
| `icp_definition.md` | always_on | — (все сегменты) |

## YAML frontmatter

Каждый файл начинается с блока:

```yaml
---
slug: playbook_horeca
title: HoReCa playbook (кофейни, рестораны, отели)
segments: [horeca, coffee_shops, restaurants, hotels]
priority: 10
always_on: false
---
```

- `segments` — список slug'ов, которые матчатся с `lead.segment`
- `priority` — побеждает файл с наибольшим приоритетом, если несколько матчатся
- `always_on: true` — файл загружается для всех лидов независимо от сегмента

## Как лоадер выбирает файлы

`app/enrichment/kb.py::select_for_segment(segment)`:
1. Загружает все `*.md` кроме README (lru_cache — один раз на процесс)
2. Всегда включает `always_on: true` файлы
3. Из сегментных выбирает один — с наибольшим `priority`, чей `segments[]` содержит `lead.segment`
4. Итого максимум 4 блока (3 always_on + 1 сегментный), суммарно до 6000 символов

## Обновление

Файлы шипятся внутри Docker-образа API. Для обновления достаточно:
1. Изменить `.md` файлы
2. Собрать и задеплоить новый образ
3. lru_cache сбрасывается при старте нового процесса

Файлы вне `apps/api/` не попадают в build context Docker и будут недоступны во время выполнения.
