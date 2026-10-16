"""CLI-скрипты, которые пишут в базу через ORM, должны видеть все таблицы.

2026-10-15 `scripts/issue_service_key.py issue` упал на проде с
`NoReferencedTableError`: скрипт импортировал только `app.external.models`,
и `workspaces` — цель внешнего ключа `service_api_keys.workspace_id` — не
попала в `Base.metadata`. Лечится импортом `app.models_registry`.

`tests/conftest.py` сам импортирует реестр, поэтому внутри pytest дефект не
виден — проверяем в чистом субпроцессе, который импортирует только скрипт,
как `python -m scripts.<name>` на сервере. Живая база не нужна: `sort_tables`
разрешает внешние ключи по одним метаданным.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]


def _run_in_fresh_process(snippet: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
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


@pytest.mark.parametrize(
    "script, model_module, model",
    [
        ("scripts.issue_service_key", "app.external.models", "ServiceApiKey"),
        ("scripts.import_prototype_data", "app.leads.models", "Lead"),
    ],
)
def test_script_resolves_foreign_keys_without_database(script, model_module, model):
    snippet = f"""
import {script}  # noqa: F401 — ровно то, что грузит `python -m {script}`
from sqlalchemy.schema import sort_tables
from {model_module} import {model}

table = {model}.__table__
sort_tables(table.metadata.tables.values())
for fk in table.foreign_keys:
    fk.column  # NoReferencedTableError, если цели нет в метаданных
print("FK_OK")
"""
    proc = _run_in_fresh_process(snippet)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("FK_OK"), (
        f"{script}: внешние ключи {model} не разрешаются без app.models_registry\n"
        f"{proc.stderr[-4000:]}"
    )
