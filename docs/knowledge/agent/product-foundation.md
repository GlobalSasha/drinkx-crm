# DrinkX Product Foundation — Agent Knowledge

> **STATUS: PLACEHOLDER — REPLACE BEFORE Phase C ENABLES THE RUNNER.**
>
> The Sprint 3.1 spec (`docs/SPRINT_3_1_LEAD_AI_AGENT.md`, Phase A NOTE)
> calls this file out as a user-supplied artefact. The real content
> hasn't been provided yet — this stub exists only so Phase B
> (migration) and Phase C (`app/lead_agent/prompts.py` file-system
> reads) can be wired against a known path.
>
> Per the spec, this is the **first** block in every system prompt
> the agent receives — for both background and coach modes. Without
> real content the agent has no grounding and will produce
> hallucinated product framing.

## Expected scope (per Sprint 3.1 spec)

The fundamental product context the agent is expected to read FIRST,
before any lead-specific data. Anchors the agent's recommendations to
DrinkX's actual offering.

## Suggested sections (skeleton — fill in)

```
## What DrinkX sells
  Smart coffee stations — hardware + service + supplies.
  Target verticals: retail, HoReCa, QSR, gas stations.

## Customer segments + buying motions
  - Enterprise direct
  - QSR / high-volume foodservice
  - Distributor / partner
  - Raw-materials / strategic
  - Private / small
  - Service / repeat
  (mapping to `lead.deal_type`)

## Value propositions per segment
  Why each segment buys; what the economic buyer cares about;
  what the champion cares about; typical objections.

## Pricing + commercial frame
  Unit economics manager can reference; what's negotiable, what's not.

## Pilot model
  How a pilot is structured, what success looks like.

## Things the agent must NEVER promise
  Discounts, custom builds, SLA commitments — escalation paths.
```

## How it gets loaded

`app/lead_agent/prompts.py` reads this file once per worker process
and caches it in `_FOUNDATION_CACHE`. Editing in production requires
a worker restart (`docker compose restart worker beat` on
`crm.drinkx.tech`).

## Provenance

Spec: `docs/SPRINT_3_1_LEAD_AI_AGENT.md` §Phase A, §Phase C
`prompts.build_system_prompt`.

The full canonical product context lives in `docs/PRD-v2.0.md`. This
file should distil the agent-relevant slice — not duplicate the PRD.
