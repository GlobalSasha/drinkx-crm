"""Единая точка регистрации ORM-моделей.

`Base.metadata` наполняется как побочный эффект импорта модулей `app/*/models.py`.
Пока каждый вызывающий собирал этот список сам, схема зависела от того, какие
модули успел импортировать тест: одиночный прогон `pytest tests/activity` получал
неполный набор таблиц и падал на внешнем ключе `contacts.company_id → companies`.

Этот модуль импортирует ВСЕ доменные модели и ничего больше — ни роутеров, ни
Celery, ни внешних клиентов, — поэтому его безопасно импортировать из тестовых
фикстур и из Alembic. Сетевых подключений он не открывает.

Добавили новый домен — допишите сюда строку. Полноту стережёт
`tests/test_models_registry_completeness.py`: он сравнивает набор таблиц после
импорта этого модуля с набором после `import app.main`.
"""
from __future__ import annotations

from app.common.models import Base  # noqa: F401 — реэкспорт для удобства

from app.activity import models as _activity_models  # noqa: F401
from app.audit import models as _audit_models  # noqa: F401
from app.auth import models as _auth_models  # noqa: F401
from app.automation_builder import models as _automation_builder_models  # noqa: F401
from app.base_update import models as _base_update_models  # noqa: F401
from app.companies import models as _companies_models  # noqa: F401
from app.contacts import models as _contacts_models  # noqa: F401
from app.custom_attributes import models as _custom_attributes_models  # noqa: F401
from app.daily_plan import models as _daily_plan_models  # noqa: F401
from app.enrichment import models as _enrichment_models  # noqa: F401
from app.external import models as _external_models  # noqa: F401
from app.followups import models as _followups_models  # noqa: F401
from app.forms import models as _forms_models  # noqa: F401
from app.import_export import models as _import_export_models  # noqa: F401
from app.inbox import models as _inbox_models  # noqa: F401
from app.lead_sources import models as _lead_sources_models  # noqa: F401
from app.leads import models as _leads_models  # noqa: F401
from app.llm_usage import models as _llm_usage_models  # noqa: F401
from app.notes import models as _notes_models  # noqa: F401
from app.notifications import models as _notifications_models  # noqa: F401
from app.pipelines import models as _pipelines_models  # noqa: F401
from app.presence import models as _presence_models  # noqa: F401
from app.quotas import models as _quotas_models  # noqa: F401
from app.quote import models as _quote_models  # noqa: F401
from app.reminders import models as _reminders_models  # noqa: F401
from app.template import models as _template_models  # noqa: F401
from app.utm import models as _utm_models  # noqa: F401

__all__ = ["Base"]
