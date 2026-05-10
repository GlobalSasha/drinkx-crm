FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Build context is the repo root (see infra/production/docker-compose.yml).
# All source paths are repo-relative; image layout under /app stays the same.

# Install deps first for caching
COPY apps/api/pyproject.toml apps/api/uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Copy source
COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./
COPY apps/api/scripts ./scripts
COPY apps/api/knowledge ./knowledge

# Lead AI Agent — Sprint 3.1 reads `docs/skills/lead-ai-agent-skill.md`
# and `docs/knowledge/agent/product-foundation.md` from the filesystem
# at process start. Without this COPY the agent runs with an empty
# foundation block and a one-shot `lead_agent.knowledge.repo_root_missing`
# warning — degraded but functional. With it, prompts include the full
# 7k-char product context.
COPY docs ./docs

EXPOSE 8000

# Run migrations on startup, then boot the API.
# In multi-replica deployments only one replica should run migrations — fine for now (single replica).
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
