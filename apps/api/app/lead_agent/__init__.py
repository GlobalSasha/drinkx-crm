"""Lead AI Agent — Sprint 3.1 Phase C.

Single agent inside the lead card with two modes:
  - Background  → `runner.get_suggestion(lead)`  → MiMo Flash via TaskType.prefilter
  - Foreground  → `runner.chat(lead, message, history)` → MiMo Pro via TaskType.sales_coach

Knowledge sources are read once at process start (lru_cache) from
`docs/skills/lead-ai-agent-skill.md` and `docs/knowledge/agent/product-foundation.md`
and injected into the LLM system prompt — no DB / no Redis cache for
the prompt assembly path.

ADR-018 fallback chain (MiMo → Anthropic → Gemini → DeepSeek) is
inherited via `app.enrichment.providers.factory.complete_with_fallback`;
this package does NOT add its own provider abstraction.
"""
