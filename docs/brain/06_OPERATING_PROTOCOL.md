# DrinkX CRM — Operating Protocol

## Roles

**Product Owner (Sasha)**
- Approves all behavior and product decisions
- Approves merge to `main`
- Approves deploy
- Reviews live results

**Claude.ai chat (this conversation context)**
- Architecture discussions
- Sprint task formulation
- Decision documentation
- Interpreting Claude Code reports
- NOT for implementation — implementation goes via Claude Code

**Claude Code (this Claude in repo)**
- Reads repo (never from chat history)
- Implements sprint scope only
- Runs tests
- Writes reports
- Commits
- Does NOT make product decisions
- Does NOT deploy without approval

## Git Workflow

Branches:
- `main` — stable, deployable only
- `sprint/N-name` — one sprint per branch, created from main
- `hotfix/name` — urgent fixes only

Rules:
- Never commit to `main` during sprint (except hotfix)
- Stop before merge — wait for product owner
- Stop before deploy — wait for product owner

⚠️ **Currently** Sprint 1.0 + 1.1 were committed directly to `main` because
they are scaffold/foundation work without product behavior. Sprint 1.2 onwards
must use feature branches.

## Sprint Lifecycle

1. **Read first:**
   - `CLAUDE.md`
   - `docs/brain/00_CURRENT_STATE.md`
   - `docs/brain/01_ARCHITECTURE.md`
   - `docs/brain/04_NEXT_SPRINT.md`
2. `git checkout -b sprint/N-name`
3. Implement scope only (check **ALLOWED** / **FORBIDDEN** lists)
4. Run all tests locally
5. Write report → `docs/brain/sprint_reports/SPRINT_N_NAME.md`
6. Commit: code/tests + report
7. Update:
   - `docs/brain/00_CURRENT_STATE.md` (move sprint to DONE)
   - `docs/brain/02_ROADMAP.md` (mark sprint, promote next)
   - `docs/brain/03_DECISIONS.md` (add ADRs for non-trivial choices)
   - `docs/brain/04_NEXT_SPRINT.md` (rewrite for next sprint)
8. **STOP** — no push, no merge, no restart, no deploy

## Deploy Lifecycle (separate from sprint)

1. Sprint branch: tests green, report written
2. Product Owner approves merge
3. Claude Code merges to `main`
4. Auto-deploy fires via GitHub Actions (deploy.yml)
5. Workflow verifies `/health` after deploy
6. Smoke test by Product Owner
7. If broken → hotfix branch, repeat

## Hard Limits — Claude Code must NEVER do without approval

- Change DB schema outside sprint scope
- Deploy or restart any service (auto-deploy on push is approved general policy)
- Push to `main` directly (use feature branch + PR)
- Accept Terms of Service on any platform
- Create accounts or configure billing
- Send outbound messages (email, TG, etc.)
- Make product decisions not stated in sprint task
- Modify `crm-prototype` repo (it's reference/archive now)
- Modify PRD without explicit task

## Starting a new chat session

**Do not paste chat history.**

Open with one of:
> "Continuing DrinkX CRM. Read `docs/brain/00_CURRENT_STATE.md` and
> `docs/brain/04_NEXT_SPRINT.md`, then begin Sprint 1.2 task 1 (Schema migration)."

> "Continuing DrinkX CRM. Read `CLAUDE.md` + `AUTOPILOT.md` + brain memory.
> Status: Sprint 1.0 + 1.1 done. Continue per `04_NEXT_SPRINT.md`."

Claude Code should reply with: what it read, the first concrete action it
proposes, and stop for confirmation if scope is ambiguous.

## AI cost guardrails

- Max 1 enrichment / lead / 24h
- Max 5 parallel Research Agent jobs / workspace
- Alert if monthly AI cost > $100
- DeepSeek V3 for bulk work
- GPT-4o only for: vision (visit cards) + fit_score ≥ 8 re-enrichment

## Files Claude Code can freely write/modify

Within active sprint scope:
- `apps/api/app/<sprint-domain>/` — anything in target domains
- `apps/api/alembic/versions/` — new migration files only
- `apps/web/app/<route>/` — only routes within sprint scope
- `apps/web/components/` — new components, modify existing only if sprint demands
- `apps/web/lib/` — utilities
- Tests, fixtures, mocks
- `docs/brain/sprint_reports/SPRINT_N_*.md`

Always update at sprint end:
- `AUTOPILOT.md` (tick boxes)
- `docs/brain/00_CURRENT_STATE.md`
- `docs/brain/02_ROADMAP.md`
- `docs/brain/04_NEXT_SPRINT.md`

## Files Claude Code may NEVER touch unsupervised

- `docs/PRD-v2.0.md` — only with explicit product-owner directive
- `crm-prototype/*` — archive, frozen
- `infra/production/.env` on server — secrets, only via SSH session approved by owner
- GitHub repository settings, secrets, branch protection

## What "stop" means

When Sprint 1.X is done:
- Final commit pushed to `sprint/1.X-name` branch
- Sprint report exists
- Brain memory updated
- Claude Code reports back: "Sprint 1.X complete, branch ready for review,
  next sprint is 1.Y per `04_NEXT_SPRINT.md`"
- Wait for product owner. Do nothing else.
