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

# Build-time version stamp. Read back by infra/production/deploy.sh (via
# `printenv DRINKX_GIT_SHA` inside the running container) and by GET /health,
# to prove the release that is running is the one that was shipped.
#
# Deliberately baked into the image and NOT set as a compose `environment:`
# value: a runtime variable can be attached to a stale image and would make the
# check pass without anything being rebuilt. Declared here, after the COPYs, so
# a new SHA does not invalidate the dependency layer.
ARG GIT_SHA=unknown
ENV DRINKX_GIT_SHA=${GIT_SHA}

# The same revision as an image LABEL. The deploy gate reads THIS, not the
# container's environment: `docker run -e DRINKX_GIT_SHA=...` can override an
# ENV at start-up, so a container's environment proves nothing about which
# image it came from. Labels belong to the image and cannot be set at run time.
LABEL org.opencontainers.image.revision=${GIT_SHA}

EXPOSE 8000

# Run migrations on startup, then boot the API.
# In multi-replica deployments only one replica should run migrations — fine for now (single replica).
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
