"""Реестр моделей полон — иначе одиночный прогон получает обрезанную схему.

`Base.metadata` наполняется импортами, поэтому набор таблиц зависит от порядка
импортов в процессе. Чтобы порядок не подыграл проверке, каждый замер делается в
ОТДЕЛЬНОМ чистом процессе: один импортирует только реестр, другой — только
сравниваемый модуль.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]

_SNIPPET = """
import {module}  # noqa: F401
from app.common.models import Base
print("\\n".join(sorted(Base.metadata.tables)))
"""


def _tables_in_fresh_process(module: str) -> set[str]:
    """Набор таблиц Base.metadata после импорта только этого модуля."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(API_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _SNIPPET.format(module=module)],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        pytest.fail(f"импорт {module} в чистом процессе упал:\n{proc.stderr[-4000:]}")
    return {line for line in proc.stdout.split("\n") if line.strip()}


def _domain_model_modules() -> list[str]:
    return sorted(
        f"app.{path.parent.name}.models"
        for path in (API_ROOT / "app").glob("*/models.py")
    )


def test_registry_lists_every_domain_models_module():
    """Ни один app/*/models.py не забыт — сравниваем по исходникам, без импорта."""
    source = (API_ROOT / "app" / "models_registry.py").read_text(encoding="utf-8")
    missing = [
        module
        for module in _domain_model_modules()
        if f"from app.{module.split('.')[1]} import models" not in source
        and f"from {module.rsplit('.', 1)[0]}.models import" not in source
    ]
    assert not missing, f"домены не попали в app/models_registry.py: {missing}"


def test_registry_covers_all_domain_models():
    """Реестр даёт ровно ту же схему, что импорт всех app/*/models.py подряд."""
    modules = _domain_model_modules()
    everything = "\n".join(f"import {m}" for m in modules)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(API_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            everything + "\nfrom app.common.models import Base\n"
            'print("\\n".join(sorted(Base.metadata.tables)))',
        ],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    expected = {line for line in proc.stdout.split("\n") if line.strip()}
    actual = _tables_in_fresh_process("app.models_registry")
    assert actual == expected, f"реестр не покрывает: {sorted(expected - actual)}"


def test_registry_is_superset_of_app_main():
    """Всё, что регистрирует app.main, есть и в реестре.

    Равенства тут нет намеренно: app.main не импортирует модели presence,
    quotas и utm, то есть обход `import app.main` сам давал неполную схему.
    Реестр — строгое надмножество.
    """
    registry = _tables_in_fresh_process("app.models_registry")
    via_main = _tables_in_fresh_process("app.main")
    assert via_main, "app.main не зарегистрировал ни одной таблицы"
    assert not (via_main - registry), (
        f"app.main регистрирует таблицы, которых нет в реестре: {sorted(via_main - registry)}"
    )
