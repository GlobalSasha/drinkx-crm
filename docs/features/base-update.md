# Обновление базы лидов (`base_update`)

> **Что это.** Админ-only инструмент массового пополнения базы из `.md`-карточек
> ЛПР: AI извлекает структуру (компания + контакты + бриф), дедуп пачки,
> матчинг против базы, авто-запись безопасного, спорное удерживается как
> конфликты на ревью. Новые лиды попадают в **пул с `needs_review`** — менеджер
> дочищает в карточке.
>
> Источник дизайна: `docs/superpowers/specs/2026-05-21-base-update-design.md`.
> Источник плана реализации: `docs/superpowers/plans/2026-05-22-base-update.md`.

## Скоуп

Только `.md`-файлы (формат свободный — AI разбирает сам). Одна загрузка =
одна `IngestJob`-пачка. Не синхронизация, не коннекторы.

Доступ: `admin` и `head` (см. `app.auth.dependencies.require_admin_or_head`).

## Архитектура и поток данных

```
1. UPLOAD     POST /api/base-update/jobs (multipart, ≤5 МБ суммарно)
              → IngestJob(status=pending, stats_json={"_staged_files":[…]})
              → 202 + send_task("base_update_extract")
2. EXTRACT    Celery → run_extract_and_match:
              status=extracting → для каждого файла complete_with_fallback(TaskType.lpr_extraction)
              → ExtractedCard (permissive Pydantic, никогда не падает)
3. DEDUP      pure dedup_batch по normalize_company_name; расхождения → #6
4. MATCH      status=matching → match_company:
              0 совпадений → создать (CompanyCreate + Lead в пул + needs_review)
              1 → дополнить (autofill пустых, конфликт #2 на отличиях)
              >1 → конфликт #1 (ambiguous)
5. WRITE      apply_record персистит безопасное (companies/leads/contacts services)
              status=ready; статистика в stats_json
6. RESOLVE    Админ PATCH /api/base-update/conflicts/{id} → resolution + resolved_value
7. APPLY      POST /api/base-update/jobs/{id}/apply
              → status=resolving → send_task("base_update_apply")
              → run_apply_resolutions → status=done (или ready, если деферы)
```

## Модель данных

`apps/api/app/base_update/models.py`. Все таблицы workspace-scoped, FK cascade.

| Таблица | Назначение | Ключевые поля |
|---------|------------|---------------|
| `ingest_jobs` | Одна загрузка-пачка | `status`, `file_count`, `source_filenames` (JSONB), `stats_json` (JSONB, включая `_staged_files` пока статус ≠ ready), `error` |
| `ingest_records` | Одна компания из пачки + план | `ingest_job_id` FK CASCADE, `company_name`, `normalized_name` (индекс), `extracted_json`, `match_company_id`, `match_lead_id`, `action` (created/updated/conflict/skipped), `confidence`, `error` |
| `ingest_conflicts` | Один конфликт под решение | `ingest_job_id` + `ingest_record_id` FK CASCADE, `type` (6 видов), `target_kind` (company/lead/contact/brief), `field_name`, `base_value`, `incoming_value`, `candidates_json`, `status` (open/resolved/skipped), `resolution`, `resolved_value`, `resolved_by`, `resolved_at` |

Миграция: `apps/api/alembic/versions/20260522_0036_base_update_tables.py`.

## 6 типов конфликтов

| Тип | Когда | Действия админа |
|---|---|---|
| **#1 company_ambiguous** | >1 совпадения по нормализованному имени | `pick`(resolved_value=company_id) / `keep`(создать новую) / `skip` |
| **#2 field_mismatch** | Поле в базе ≠ извлечённого (на компании) | `keep`(база) / `overwrite`(из карточки) / `manual`(resolved_value) / `skip` |
| **#3 contact_mismatch** | Контакт по имени совпал, но детали разные | `keep` / `overwrite` / `add_separate` / `skip` — **dispatch отложен (v1.1)** |
| **#4 lead_target** | >1 лида у компании, куда писать дополнение | `pick` / `keep`(создать новый) / `skip` — **dispatch отложен (v1.1)** |
| **#5 low_confidence** | `extraction_confidence` < 0.55 ИЛИ пустое имя компании | `manual` / `skip` |
| **#6 batch_duplicate** | Дубль внутри пачки + поля расходятся | `keep`(слить, всё уже слито в group.primary) / `add_separate`(пока на ревью v1.1) |

Константы порога — `app.base_update.constants.MIN_EXTRACTION_CONFIDENCE = 0.55`,
поля для diff — `DIFFABLE_FIELDS`.

## AI-извлечение

Один LLM-вызов на файл через `complete_with_fallback` (новый `TaskType.lpr_extraction`,
в `_FLASH_TASKS` — едет на быстрых моделях). Стоимость → `llm_usage` автоматически
(передаём `db=`, `workspace_id=`). Перед каждым вызовом — `has_budget_remaining`;
исчерпан → остановка с `job.error="llm_budget_exhausted"`, статус ready (частичный).

Pydantic-схема `ExtractedCard` (`schemas.py`) — **permissive**: все поля Optional+
дефолты, валидаторы `mode="before"` фильтруют мусор (не-dict в `contacts`,
неизвестные `role_type` → null, `extraction_confidence` clamp в [0,1]).
**Никогда не raise.**

## REST API (`/api/base-update/*`)

| Метод | Путь | Что делает |
|---|---|---|
| POST | `/jobs` | multipart `.md` → 202 IngestJobOut; ставит Celery `base_update_extract` |
| GET | `/jobs` | список (limit/offset, по `created_at` desc) |
| GET | `/jobs/{id}` | один job (poll'ится фронтом) |
| GET | `/jobs/{id}/conflicts?only_open=true` | список конфликтов |
| PATCH | `/conflicts/{id}` | `{resolution, resolved_value}` → CONFLICT_RESOLVED |
| POST | `/jobs/{id}/apply` | 202; ставит Celery `base_update_apply` |

Все — `Depends(require_admin_or_head)`. Multipart-загрузка проверяет
расширение `.md` и суммарный размер ≤ 5 МБ (`MAX_UPLOAD_BYTES` в `services.py`).

## Celery

Обёртки в `apps/api/app/scheduled/jobs.py`:
- `base_update_extract(job_id)` → `orchestrator.run_extract_and_match`
- `base_update_apply(job_id)` → `orchestrator.run_apply_resolutions`

Pattern — как у `run_enrichment_task`: `_build_task_engine_and_factory()`
(NullPool на задачу), `asyncio.run`, `engine.dispose()` в `finally`.

## Фронт

`/settings` → секция «Обновление базы»
(`apps/web/components/settings/BaseUpdateSection.tsx`). Три состояния:
1. **Idle** — drag-and-drop / file picker `.md`, кнопка «Загрузить и разобрать».
2. **Running** (`pending/extracting/matching/resolving`) — спиннер + статус,
   поллинг через `useIngestJob` каждые 2 с.
3. **Ready/Done** — карточки счётчиков + список открытых конфликтов
   (`ConflictCard.tsx`) + «Применить решения» (disabled пока есть open).

Хуки — `apps/web/lib/hooks/use-base-update.ts`:
`useIngestJob`, `useIngestJobConflicts`, `useIngestJobs`,
`useCreateIngestJob` (multipart через `api.postFormData`), `useResolveConflict`,
`useApplyResolutions`.

## Что НЕ делает (явно вне скоупа v1)

- Триграммный fuzzy-матч похожих имён (только точное по нормализованному).
  Кейс «1 точное + N похожих» сводится к `update` (точное), похожие игнорируются.
- Авто-write для `#3 contact_mismatch` и `#4 lead_target` resolution —
  админ может закрыть конфликты, реальный апдейт контакта/привязки лида в БД
  отложен на v1.1. См. `_decide_apply` → `("deferred", ...)`.
- AI-бриф в апдейт-пути: пока всегда добавляем брифа НЕ перетираем существующий.

## ⚠️ Подводные камни

1. **Маппинг поля `segment`**: в `ExtractedCompany.segment`, в `CompanyCreate`
   называется `primary_segment`, на `Lead` — `segment`. Не путать. См.
   `_diff_company_fields` (используется `primary_segment` как `field_name` в
   конфликте — applier должен передать тем же ключом в `CompanyUpdate(**{f: v})`).
2. **Создание пула**: лид строится **прямо как `Lead(...)`** (по образцу
   `_create_lead_from_email_payload`), НЕ через `leads.services.create_lead`
   (тот назначает на пользователя и ставит `assigned`). Поля обязательные:
   `pipeline_id`, `stage_id` от `pipelines_repo.get_default_first_stage` —
   она может вернуть `None` (нет дефолт-пайплайна) → `record.error` + конфликт.
3. **Дикси ≠ X5** (memory `lead-data-diksi-x5`): не привязывайте Дикси к
   X5/`purchase@x5.ru`. Проверено в e2e (`test_e2e_extract_match_apply`).
4. **`_staged_files` в `stats_json`** — пока статус ≠ ready там лежат тексты
   .md. Орхестратор очищает ключ после обработки. Не отдавайте `stats_json`
   во фронт без фильтра, если беспокоит размер; в текущем UI пока ок (5 МБ).
5. **Регистрация модели** в `scheduled/celery_app.py` И `alembic/env.py`
   обязательна для обоих side-effect import блоков. Иначе worker / autogen
   не увидят таблицы.
6. **`complete_with_fallback` сам записывает `llm_usage`** при наличии
   `db=` + `workspace_id=`. Не дублируйте.
7. **e2e (`tests/base_update/test_e2e.py`)** skipif-guarded на
   `POSTGRES_AVAILABLE` — гоняется только на CI с тестовой БД.

## Тестовое покрытие (по состоянию на 2026-05-23)

```
tests/base_update/
  test_schemas.py            4 ✓ — permissive validators
  test_extractor.py          3 ✓ — LLM-mocked, code-fence, non-JSON
  test_dedup.py              6 ✓ — #6 grouping, primary card, edge cases
  test_matcher.py           10 ✓ — classify_field, match_contact, low_confidence
  test_services_match.py     4 ✓ — _match_from_rows pure
  test_services_apply.py    13 ✓ — apply_record early-returns + _diff + _decide_apply
  test_orchestrator_smoke.py 4 ✓ — staged-files helpers
  test_api.py                8 ✓ — _build_staged_files + DTOs + routes registered
  test_e2e.py                1 — skipif POSTGRES_AVAILABLE (CI only)
  ──────────────────────────────
  Итого                     52 passed + 1 skipped
```
