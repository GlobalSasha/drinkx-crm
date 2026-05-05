.PHONY: help dev web api db.up db.down db.migrate db.shell redis.shell install fmt lint test

help:
	@echo "DrinkX CRM — common commands"
	@echo ""
	@echo "  make install      Install all deps (pnpm + uv)"
	@echo "  make dev          Run web + api locally (needs db.up first)"
	@echo "  make web          Web only (Next.js, port 3000)"
	@echo "  make api          API only (FastAPI, port 8000)"
	@echo "  make db.up        Start Postgres + Redis via docker-compose"
	@echo "  make db.down      Stop them"
	@echo "  make db.migrate   Run Alembic migrations"
	@echo "  make db.shell     psql into local Postgres"
	@echo "  make redis.shell  redis-cli into local Redis"
	@echo "  make fmt          Format code (prettier + ruff)"
	@echo "  make lint         Lint (eslint + ruff + mypy)"
	@echo "  make test         Run all tests"

install:
	pnpm install
	cd apps/api && uv sync

db.up:
	docker compose -f infra/docker/docker-compose.yml up -d
	@echo "Postgres on :5432, Redis on :6379, Mailhog UI on :8025"

db.down:
	docker compose -f infra/docker/docker-compose.yml down

db.migrate:
	cd apps/api && uv run alembic upgrade head

db.shell:
	docker compose -f infra/docker/docker-compose.yml exec postgres psql -U drinkx -d drinkx_crm

redis.shell:
	docker compose -f infra/docker/docker-compose.yml exec redis redis-cli

web:
	cd apps/web && pnpm dev

api:
	cd apps/api && uv run fastapi dev app/main.py

dev:
	@echo "Run 'make web' and 'make api' in separate terminals"
	@echo "Or use foreman / overmind / tmux to run both"

fmt:
	pnpm format
	cd apps/api && uv run ruff format .

lint:
	pnpm lint
	cd apps/api && uv run ruff check . && uv run mypy app

test:
	cd apps/api && uv run pytest
	cd apps/web && pnpm test
