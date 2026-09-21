"""Прод-энтрипоинт `uvicorn app.main:app` не видел домен `utm` — регрессия.

Коммит b4fb39a добавил в `app/leads/models.py` строковые ForeignKey на
`utm_sources` / `utm_mediums` / `utm_campaigns`, но `app.main` не импортирует
`app.utm.models`. `Base.metadata` наполняется как побочный эффект импорта
`app/*/models.py`, поэтому в проде эти таблицы-цели отсутствуют из схемы,
и первый `POST /leads` падает на flush с `NoReferencedTableError`. Celery
(`app/scheduled/celery_app.py`) и тесты (`tests/conftest.py`) импортируют
`app.models_registry` и потому дефект не видят — отсюда обязательный чистый
субпроцесс, импортирующий ТОЛЬКО `app.main`, как это делает `uvicorn`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]


def _run_in_fresh_process(snippet: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    """Прогон сниппета в отдельном интерпретаторе — только `app.main` в scope."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(API_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_startup_module_matches_the_production_entrypoint():
    """Dockerfile CMD должен называть `app.main:app` — иначе этот файл проверяет не то."""
    dockerfile = (API_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "app.main:app" in dockerfile, (
        "Dockerfile CMD больше не называет app.main:app — тесты в этом файле "
        "проверяют не тот энтрипоинт, обновите их вместе с Dockerfile"
    )


def test_api_startup_registers_every_foreign_key_target():
    """У каждого ForeignKey в схеме, наполненной только `import app.main`, есть таблица-цель.

    `fk.target_fullname` — публичный атрибут SQLAlchemy (вида "table.column"),
    в отличие от `fk._table_key()` из test_models_registry_completeness.py.
    Это durable guard: он не зависит от того, где именно упадёт flush.
    """
    snippet = """
import app.main  # noqa: F401 — ровно то, что импортирует uvicorn app.main:app
from app.common.models import Base

tables = set(Base.metadata.tables)
missing = []
for table in Base.metadata.tables.values():
    for fk in table.foreign_keys:
        # target_fullname — "таблица.колонка", а для таблицы со схемой
        # "схема.таблица.колонка". rsplit отрезает именно колонку, поэтому
        # ключ совпадает с ключом в Base.metadata.tables в обоих случаях.
        target = fk.target_fullname.rsplit(".", 1)[0]
        if target not in tables:
            missing.append((table.name, fk.parent.name, target))

import json
print(json.dumps(sorted(missing)))
"""
    proc = _run_in_fresh_process(snippet)
    if proc.returncode != 0:
        pytest.fail(f"импорт app.main в чистом процессе упал:\n{proc.stderr[-4000:]}")

    import json

    missing = json.loads(proc.stdout.strip().splitlines()[-1])
    assert not missing, (
        f"после `import app.main` в Base.metadata отсутствуют таблицы-цели "
        f"для этих ForeignKey (table, column, missing_target): {missing}"
    )


def test_creating_a_lead_resolves_its_foreign_keys_after_startup():
    """Воспроизводит именно тот кадр, в котором падает прод-трейсбек.

    Прод-трейсбек падал в `orm/mapper.py` внутри `_sorted_tables`, куда
    `orm/persistence.py:save_obj` заглядывает во время flush. Это приватный
    атрибут SQLAlchemy, и мы намеренно его пиним здесь — тест выше
    (`test_api_startup_registers_every_foreign_key_target`) через публичный
    `fk.target_fullname` — durable guard на будущее; этот тест — дословное
    воспроизведение прод-кадра, чтобы регрессия была доказана, а не только
    предположена.
    """
    snippet = """
import app.main  # noqa: F401 — ровно то, что импортирует uvicorn app.main:app
from sqlalchemy import inspect as sa_inspect
from app.leads.models import Lead

try:
    sa_inspect(Lead)._sorted_tables
    print("SORTED_TABLES_OK")
except Exception as exc:
    print(f"SORTED_TABLES_RAISED:{type(exc).__name__}:{exc}")
"""
    proc = _run_in_fresh_process(snippet)
    if proc.returncode != 0:
        pytest.fail(f"импорт app.main в чистом процессе упал:\n{proc.stderr[-4000:]}")

    output = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    assert output == "SORTED_TABLES_OK", (
        f"inspect(Lead)._sorted_tables упал в проде-эквивалентном процессе: {output}"
    )
