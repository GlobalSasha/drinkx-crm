# Next Sprint: Infrastructure & Polish

Status: **READY TO START**

Sprint 3.1 (Lead AI Agent «Чак») закрыт. Перед следующим продуктовым
спринтом — стабилизация инфраструктуры и доводка экранов, которые
не успели в волну UI-обновлений.

## Приоритет 1 — CI + Branch Protection (HIGH)

Сейчас любой пуш идёт напрямую в main без проверок. Это уже
кусается: за май 2026 три деплоя подряд падали на typed-route /
Suspense ошибках, которые `tsc --noEmit` пропускает, а ловит только
`next build` (см. PR [#15](https://github.com/GlobalSasha/drinkx-crm/pull/15)).

- `apps/web/.github/workflows/web.yml` — `pnpm install` → `tsc --noEmit` → `eslint .` → `pnpm build`
- `apps/api/.github/workflows/api.yml` — `uv sync` → `pytest --collect-only` → `pytest -q -m "not slow"` → `mypy app/`
- Branch protection на `main`: require PR + 1 passing check; запретить force-push.

## Приоритет 2 — Design System на оставшиеся экраны (MEDIUM)

UI-волна (Sprint 3.0 в roadmap) обновила большинство экранов под
`C.*` токены и brand-accent палитру, но три остались на старых
токенах `bg-canvas / text-accent`-зелёный:

- `/inbox` — `apps/web/app/(app)/inbox/page.tsx`
- `/settings` — `apps/web/app/(app)/settings/page.tsx` + sub-sections (`PipelinesSection`, `TeamSection`, `ChannelsSection`, `AISection`, `CustomFieldsSection`, `TemplatesSection`)
- `/automations` — `apps/web/app/(app)/automations/page.tsx`

Подход: пройтись `bg-accent → bg-brand-accent`, `text-accent → text-brand-accent-text`, при необходимости заменить «свободный» Tailwind на `${C.button.primary}` / `${C.color.text}` / `${C.bodySm}`. Сверять с `apps/web/lib/design-system.ts`.

## Приоритет 3 — Pipeline quick-filters (MEDIUM)

`?filter=rotting` и `?filter=followup_overdue` сейчас читаются в
`pipeline/page.tsx`, но не применяются — в `usePipelineStore` нет
полей и экшенов под эти быстрые фильтры (отмечено в PR
[#11](https://github.com/GlobalSasha/drinkx-crm/pull/11)). Эффект уже
подписан на `filterParam` через зависимости `useEffect` — нужно
дописать только тело применения.

- Добавить в `apps/web/lib/store/pipeline-store.ts`: `quickFilter: 'rotting' | 'followup_overdue' | null` + `setQuickFilter`.
- Pipeline page: применять `quickFilter` к видимым картам (клиентская фильтрация поверх загруженных) или прокидывать в `useLeads` filter (требует `is_rotting` / `followup_status` фильтров на бэке — проверить, что доступно).
- Когда применение готово — UI-чип в `PipelineHeader` для ручного включения / сброса.

## Приоритет 4 — Sentry activation (LOW, откладывалось с Sprint 2.7 G1)

Лазенка уже стоит — capture chokepoint и error boundaries добавлены
в Sprint 2.7 G1, но без DSN они no-op'ят:

- Backend: `SENTRY_DSN` env var → `init_sentry_if_dsn(settings)` уже подхватывает.
- Frontend: `cd /opt/drinkx-crm/apps/web && pnpm add @sentry/nextjs` + `NEXT_PUBLIC_SENTRY_DSN` env var → `apps/web/lib/sentry.ts` слетит с warn-once на live.
- Накрыть: cron-swallows в `daily_plan_runner` / `digest_runner` / `automation_builder.safe_evaluate_trigger` (уже обёрнуты `capture()` через `app/common/sentry_capture.py`); `audit.log` swallow; новые свапы `lead_agent.{refresh_suggestion_async,scan_silence_async}` (Sprint 3.1 — добавить аналогичные обёртки).
- Перед активацией — настроить Sentry-side rate-limit, иначе шумные cron'ы выжгут 5k/мес free-tier за неделю.

## Tech debt (не блокирует, но накопилось)

- **`COPY docs ./docs` в `apps/api/Dockerfile`** — мусор после переезда knowledge-файлов в `apps/api/knowledge/agent/` (Sprint 3.1 PR #20). Сейчас копирует только спеки (`PRD-v2.0.md`, `brain/`, ADR'ы) в контейнер — безвредно, но лишний слой. Убрать одним маленьким PR.
- **`?filter=rotting` / `?filter=followup_overdue` deep-link** — ждёт п.3.
- **Маршруты `/notifications`, `/team`, `/knowledge`** — упоминаются в `CLAUDE.md` IA, но страниц нет: переход даёт 404. Уведомления открываются только через bell-drawer в AppShell. Решить: либо завести страницы, либо снять упоминания из `CLAUDE.md`.
- **`pg_dump` cron на хосте** — `scripts/pg_dump_backup.sh` + `docs/crontab.example` лежат в репо с Sprint 2.4 G5; оператор ещё не повесил на хосте. Открытый риск с момента launch checklist'а Sprint 1.5.
- **`AgentSuggestion` не несёт `manager_action`** — PATCH-эндпоинт «отметить совет принятым / проигнорированным» из спеки Sprint 3.1 не реализован. Текущее поведение: ✕ в баннере прячет его на сессию, следующий refresh пишет свежий — без аудита того, что менеджер сделал. Расширить схему + добавить PATCH когда станет нужно для метрик качества.
- **Phase E `inbox/processor.py` countdown=900** — спека просила 15-минутную задержку перед агентом, проверить что parallel-агент в PR [#22](https://github.com/GlobalSasha/drinkx-crm/pull/22) реализовал именно так. Если nope — добавить `countdown=900` в `apply_async`.
- **Stage-replacement preview в PipelineEditor** — карри с Sprint 2.3, при удалении/переименовании стадий лиды улетают в `stage_id=NULL`, UI не предупреждает. Sprint 2.4 polish carryover.
- **Multi-clause condition UI** в Automation Builder — бэк поддерживает n-clause, фронт пока на одной строке.

## Следующий free migration index

`0023` — последняя занятая `0022_lead_agent_state` (Sprint 3.1 Phase B).

## После завершения

`docs/SMOKE_CHECKLIST_3_2.md` (или какой будет следующий) должен
включить:
- [ ] CI workflow на тестовом PR — все 3 шага зелёные
- [ ] Force-push в main отвергается с понятной ошибкой
- [ ] `/inbox`, `/settings`, `/automations` — кнопки primary видно как brand-accent (orange), не зелёный
- [ ] `?filter=rotting` на `/pipeline` оставляет только rotting карточки; `?filter=followup_overdue` — только просроченные follow-up
- [ ] Sentry получает test event с прода (backend `SENTRY_DSN` set + frontend Next.js plugin installed)
- [ ] Уже работающие E2E smoke (Sprint 2.4 / 2.5 / 2.6 / 2.7 / 3.1 чек-листы) не сломались
