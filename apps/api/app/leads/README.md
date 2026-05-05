# app/leads

Leads domain. Owns:

- CRUD for `leads`
- Search and filter (segment, city, stage, assignee, query)
- Stage transitions delegate to `app/automation/stage_change.py`
- Triggers initial enrichment via `app/enrichment/orchestrator.py`

Files (created in Sprint 1.2):

- `models.py` — `Lead` ORM model with `ai_data` JSON column
- `schemas.py` — Pydantic DTOs
- `repositories.py` — query helpers (filter chain)
- `services.py` — high-level operations
- `tasks.py` — Celery tasks (re-enrich queue)
- `routers.py` — `/leads` REST + WebSocket subscribers

See AUTOPILOT.md §1.2.2.
