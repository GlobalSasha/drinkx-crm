# Lead AI Agent — Behavioural Skill

> **STATUS: PLACEHOLDER — REPLACE BEFORE Phase C ENABLES THE RUNNER.**
>
> The Sprint 3.1 spec (`docs/SPRINT_3_1_LEAD_AI_AGENT.md`, Phase A NOTE)
> calls this file out as a user-supplied artefact. The real content
> hasn't been provided yet — this stub exists only so Phase B
> (migration) and Phase C (`app/lead_agent/prompts.py` file-system
> reads) can be wired against a known path.
>
> When Phase C lands and tries to load this file at runtime, the
> agent will produce nonsense unless the real skill specification
> has been dropped in.

## Expected scope (per Sprint 3.1 spec)

The skill is the **system-prompt half** that defines how the agent
behaves. `product-foundation.md` (sibling artefact) covers WHAT the
product is; this file covers HOW the agent should think and respond.

Both sections are read at worker start and cached in
`_FOUNDATION_CACHE` / `_SKILL_CACHE` (see Phase C `prompts.py`).

`prompts.build_system_prompt()` consumes this file and selects
sections based on `mode`:

- `mode="background"` — used by the Celery silence/SPIN scanner; emits
  one `AgentSuggestion` JSON object or `silent: true`.
- `mode="coach"` — used by the foreground Sales Coach drawer; emits
  free-form chat replies.

## Required sections (skeleton — fill in)

```
## Role + posture
  How the agent presents itself, tone, scope of advice.

## Sales methodology — SPIN
  How to detect the current SPIN phase from `activities`.
  How to flag missing pieces (`spin_notes`, `spin_phase`).

## Triggers (background mode)
  Mapping of trigger reason → expected suggestion shape:
    silence_3d, silence_7d, spin_gap, rotting,
    stage_changed, new_inbound, no_economic_buyer

## Output contracts
  Strict JSON for background mode (AgentSuggestion shape — see spec §C runner.py).
  Free-form Russian text for coach mode (with quick-action chips).

## Guardrails
  - Never auto-act on the lead without the manager.
  - Never invent contact data not in `LeadAgentContext`.
  - On parse failure: emit `silent: true` and abort, do NOT crash.

## Russian-language constraints
  Output language, terminology consistent with the CRM UI labels.
```

## How it gets loaded

`prompts.py` reads this file once per worker process and caches it.
Editing the file in production requires a worker restart
(`docker compose restart worker beat` on `crm.drinkx.tech`).

## Provenance

Spec: `docs/SPRINT_3_1_LEAD_AI_AGENT.md` §Phase A, §Phase C `prompts.py`,
§Phase C `runner.py` (AgentSuggestion shape).
