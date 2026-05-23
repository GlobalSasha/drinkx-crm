# Вложения файлов к задачам

> **Что это.** К задаче в карточке лида менеджер прикрепляет файл
> (PDF, изображение, документ, таблица, аудио, текст; ≤25 МБ). Файлы лежат
> в приватном бакете Supabase Storage `lead-files`; ссылка для скачивания
> подписывается на 5 минут.
>
> Источник плана: `docs/superpowers/plans/2026-05-23-task-file-attachments.md`.

## Скоуп

- **Поиск:** по имени файла + тексту тела активности + **извлечённому контенту** (PDF через `pypdf`, текст .txt/.md/.csv/.rtf через utf-8 декод, **audio через OpenAI Whisper API** — mp3/wav/m4a/ogg). Содержимое индексируется асинхронно после загрузки — Celery-задача скачивает файл из бакета и пишет excerpt (≤100 КБ) в `Activity.payload_json.extracted_text`. Whisper включается автоматически если `OPENAI_API_KEY` установлен; без ключа audio тихо пропускается (поиск просто не матчит по содержимому). **DOC/DOCX/XLSX отложены до v1.2** — требуют openpyxl/mammoth. ILIKE на бэке +
  клиентский фильтр задач). Извлечение содержимого (текст PDF, STT аудио) —
  следующая итерация.
- **Доступ:** любой `current_user` лида (workspace-scoped через
  `_get_lead_or_raise` или JOIN на `Lead`).
- **Лимит:** 25 МБ на файл, расширения по whitelist (см. ниже).

## Архитектура

Один файл = одна строка `Activity(type="file")`. Связь с задачей — через
`payload_json.parent_task_id = <task_activity_id>`. Schema-миграции для самой
связи не понадобилось (`Activity.file_url`, `Activity.file_kind`,
`ActivityType.file` уже были); добавлен только индекс для быстрого lookup.

```
1. UPLOAD      POST /leads/{lead_id}/tasks/{task_id}/files  (multipart: file + caption?)
               ↓
               classify_upload  — extension whitelist + size cap
               ↓
               Activity(type=file, payload_json={parent_task_id, file_name, file_size})
               ↓
               db.flush()  → activity.id готов
               ↓
               SupabaseStorageClient.upload(key=ws/lead/act/slug, bytes, content_type)
               ↓
               activity.file_url = key  (это путь в бакете, НЕ signed URL)
               ↓
               db.commit() + 201 TaskFileOut

2. LIST        GET /leads/{lead_id}/tasks/{task_id}/files[?q=...]
               ↓
               WHERE payload_json->>'parent_task_id' = task_id  (партиальный индекс)
               ↓
               optional ILIKE на file_name + body

3. DOWNLOAD    GET /activities/{id}/download
               ↓
               JOIN Lead → проверка workspace_id (у Activity нет своего workspace_id)
               ↓
               SupabaseStorageClient.create_signed_url(key, expires_in=300)
               ↓
               200 {url, expires_in: 300}

4. DELETE      DELETE /activities/{id}/file
               ↓
               storage.delete (best-effort, 404 swallowed)
               ↓
               db.delete(activity) + commit
```

## Storage layout

```
lead-files (private bucket)
└── {workspace_id}/
    └── {lead_id}/
        └── {activity_id}/
            └── {slugged-filename.ext}
```

Slug: lowercase, ASCII-фолдинг с транслитерацией кириллицы, non-[a-z0-9.] схлопывается
в `-`, расширение сохраняется (`Коммерческое предложение v3.pdf` →
`kommercheskoe-predlozhenie-v3.pdf`). См. `app/storage/paths.py`.

## REST API

| Метод | Путь | Что делает |
|---|---|---|
| POST | `/leads/{lid}/tasks/{tid}/files` | multipart `file` + optional `caption` → 201 `TaskFileOut` |
| GET  | `/leads/{lid}/tasks/{tid}/files?q=…` | список файлов задачи (ILIKE по имени + body) |
| GET  | `/activities/{id}/download` | 5-min signed URL (workspace-scope через JOIN на Lead) |
| DELETE | `/activities/{id}/file` | удаление storage + Activity (best-effort) |

Все — `Depends(current_user)`. На multipart-upload: per-file bounded read
(`f.read(MAX_FILE_BYTES+1)`) до любых других проверок, пустой файл → 400,
без расширения / неподдерживаемое → 400, >25 МБ → 413.

## Whitelist расширений → kind

```
pdf            → pdf
doc, docx      → document
xls, xlsx, csv → spreadsheet
txt, md, rtf   → text
png, jpg/jpeg, gif, webp, heic → image
mp3, wav, m4a, ogg            → audio
```

Двойное расширение (`invoice.pdf.exe`) ловится по последнему — `.exe` не в
whitelist → 400. `kind` сохраняется в `Activity.file_kind` и используется
во фронте для иконки.

## Frontend

- **`TasksTab.tsx`** — добавлены: поиск по задачам (фильтр по title + body,
  плюс пробрасывает `q` в `useTaskFiles`); каждый task разворачивается через
  кнопку «📎 ⌄» в инлайн-панель с `TaskFilesList` + `TaskFileDropzone`.
- **`TaskFileDropzone.tsx`** — drag-and-drop ИЛИ file input, превью + caption
  + кнопка «Загрузить», 25 МБ cap клиентский (бэк всё равно валидирует).
- **`TaskFilesList.tsx`** — список с иконкой по `file_kind`, кнопки Download
  (через 5-мин signed URL) + Delete (`window.confirm` — файл легко
  перезагрузить, кастомная модалка избыточна).

Хуки в `apps/web/lib/hooks/use-task-files.ts`:
`useTaskFiles`, `useUploadTaskFile` (через `api.postFormData`),
`useDownloadTaskFile`, `useDeleteTaskFile`.

## Celery

Еженедельный `purge_orphan_storage_files` (воскресенье 03:30 UTC,
`scheduled/jobs.py`):
- листает бакет (`SupabaseStorageClient.list_objects(prefix="", limit=1000)`)
- кросс-проверяет с `SELECT file_url FROM activities WHERE type='file'`
- удаляет ключи, **которым >7 дней** и которых нет в живых строках
  (защита от гонок с in-flight upload'ами)
- best-effort: ошибка delete → лог + продолжение

## DB-индекс (миграция 0037)

```sql
CREATE INDEX ix_activities_parent_task_id
ON activities ((payload_json->>'parent_task_id'))
WHERE type = 'file'
```

Партиальный → маленький (90%+ активностей — это comment/task/email/system).

## ⚠️ Подводные камни

1. **Storage и Activity НЕ транзакционны.** Если `storage.upload` падает
   после `db.flush()`, строка существует с `file_url=<key>` без объекта в
   бакете. Текущий роутер коммитит только при успехе upload'а; orphan-purger
   подчищает потенциальные сироты в обратную сторону (объект без строки).
2. **`Activity.file_url` хранит storage-путь, НЕ signed URL.** Signed URL
   генерится on-demand на 5 минут — иначе любая сохранённая ссылка протухнет.
3. **`Activity` НЕ имеет колонки `workspace_id`** — workspace scope везде
   через `Lead.workspace_id`. Для путей `POST/GET /leads/.../tasks/...`
   используется `_get_lead_or_raise`; для путей `/activities/{id}/...` —
   явный JOIN на `Lead`.
4. **Двойное расширение** (`invoice.pdf.exe`) ловится по последнему: `.exe`
   не в whitelist → 400.
5. **`window.confirm` в `TaskFilesList`** — намеренно. Файлы заменяемы
   (re-upload), inline-двушаговое подтверждение в плотном списке навредит
   UX. Если аудит снова заденет — переехать на pattern из `NeedsReviewRow`.
6. **Бакет приватный, RLS НЕ настроен.** Фронт ходит к Supabase Storage
   только через наш бэкенд (бэк использует `SUPABASE_SECRET_KEY`). Если
   когда-нибудь захотим публичные превью изображений — настраиваем RLS
   и/или public bucket с CDN.
7. **`api.postFormData`** в `api-client.ts` (добавлен в PR #66) НЕ ставит
   `Content-Type` руками — браузер сам выставляет `multipart/form-data` с
   boundary. Не сломать.
8. **e2e на реальный Supabase Storage** — отдельным этапом, гонится только
   на CI с валидными `SUPABASE_URL` + `SUPABASE_SECRET_KEY` + `SUPABASE_STORAGE_BUCKET`.

## Тестовое покрытие (2026-05-23)

```
tests/storage/
  test_paths.py             4 ✓  — slug + key
  test_client.py            4 ✓  — httpx-mocked upload/sign/delete
tests/activity/
  test_files_validators.py  8 ✓  — classify_upload (whitelist + size + double-ext)
  test_task_files.py        4 ✓  — upload/delete/sign service smoke
  test_files_api.py         4 ✓  — routes registered + DTO edge cases
  ───────────────────────────────
  Итого                    24 passed
```

Не закрыто юнитами (требует реального Postgres + Supabase config — гоняется на CI):
- `find_files_by_parent_task` SQL-путь.
- Реальный multipart end-to-end (upload → list → download → delete).
- `purge_orphan_storage_files` сквозной проход.
