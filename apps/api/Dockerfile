FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install deps first for caching
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Copy source
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

EXPOSE 8000

# Run migrations on startup, then boot the API.
# In multi-replica deployments only one replica should run migrations — fine for now (single replica).
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
