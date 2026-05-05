# app/auth

Auth domain. Owns:

- Verification of Supabase JWT (handed off after Google OAuth)
- Workspace bootstrap on first sign-in (creates default pipeline + 6 stages)
- User profile updates (working_hours, role, spec, max_active_deals)
- `GET /auth/me` and `PATCH /auth/me` endpoints

Files (created in Sprint 1.1):

- `models.py` — `User`, `Workspace` ORM models
- `schemas.py` — Pydantic DTOs
- `repositories.py` — DB access
- `services.py` — workspace bootstrap, JWT verify
- `routers.py` — FastAPI router
- `events.py` — domain events emitted (`user.signed_up`, `workspace.created`)

See AUTOPILOT.md §1.1.4.
