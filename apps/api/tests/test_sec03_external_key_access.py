"""SEC-03 — разведка: что на самом деле отдаёт ключ интеграции.

У `/external/v1/*` другой актор: машинный ключ `drinkx_os_...`, а не
вошедший пользователь. Здесь проверяется фактическая модель:

* ключ пространства A не видит ни карточек, ни компаний, ни контактов,
  ни агрегатов пространства B — ни списком, ни по UUID, ни фильтром;
* отсутствие ключа, неизвестный, отозванный и ключ без нужного scope
  получают отказ, а не данные;
* список и запрос по UUID пользуются одной моделью scope;
* поверхность действительно только на чтение;
* секрет не возвращается ни одним маршрутом.

Ключи создаются здесь же, живут в одноразовой базе и в логи не попадают:
в сообщениях об ошибках печатается только префикс.

Выпуск, просмотр и отзыв ключей HTTP-маршрутов не имеют вовсе — это
серверный скрипт `scripts/issue_service_key.py`. Проверяется именно это
утверждение, а не выдуманный «эндпоинт управления ключами».
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401 — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


# --- обвязка ---------------------------------------------------------------

async def _workspace(db, name: str):
    from app.auth.models import Workspace

    ws = Workspace(name=name, plan="pro", sprint_capacity_per_week=20)
    db.add(ws)
    await db.flush()
    return ws


async def _user(db, workspace_id, name: str, role: str = "manager"):
    from app.auth.models import User

    u = User(
        workspace_id=workspace_id,
        email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        name=name,
        role=role,
    )
    db.add(u)
    await db.flush()
    return u


async def _pipeline(db, workspace_id, name: str):
    from app.pipelines.models import Pipeline, Stage

    p = Pipeline(workspace_id=workspace_id, name=name, type="sales", position=0)
    db.add(p)
    await db.flush()
    s = Stage(pipeline_id=p.id, name="Новые", position=1, color="#aabbcc", rot_days=14)
    db.add(s)
    await db.flush()
    return p, s


async def _company(db, workspace_id, name: str):
    from app.companies.models import Company

    c = Company(workspace_id=workspace_id, name=name, normalized_name=name.lower())
    db.add(c)
    await db.flush()
    return c


async def _lead(db, workspace_id, *, name, owner_id=None, pipeline=None, company_id=None):
    from app.leads import repositories as repo

    data = dict(company_name=name)
    if pipeline is not None:
        data["pipeline_id"] = pipeline[0].id
        data["stage_id"] = pipeline[1].id
    if company_id is not None:
        data["company_id"] = company_id
    return await repo.create_lead(
        db, workspace_id, data,
        assigned_to=owner_id,
        assignment_status="assigned" if owner_id else "pool",
    )


async def _contact(db, workspace_id, lead_id, name: str):
    from app.contacts.models import Contact

    c = Contact(workspace_id=workspace_id, lead_id=lead_id, name=name)
    db.add(c)
    await db.flush()
    return c


async def issue_key(db, workspace_id, *, scopes=("read:core",), revoked=False) -> str:
    """Временный ключ для одного прогона. Возвращает полный токен."""
    from datetime import datetime, timezone

    from app.external import keys
    from app.external.models import ServiceApiKey

    token, key_hash = keys.generate_key()
    row = ServiceApiKey(
        workspace_id=workspace_id,
        name=f"recon-{uuid.uuid4().hex[:6]}",
        key_hash=key_hash,
        scopes=list(scopes),
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    db.add(row)
    await db.flush()
    await db.commit()
    return token


async def ext(db, token: str | None, path: str):
    """GET на внешнюю поверхность с машинным ключом (или без него)."""
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            return await c.get(path, headers=headers)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def two_workspaces(db):
    """Два пространства с полным набором данных и по ключу на каждое."""
    a = await _workspace(db, "Пространство A")
    b = await _workspace(db, "Пространство B")

    a_user = await _user(db, a.id, "Anna")
    b_user = await _user(db, b.id, "Boris")

    a_pipe = await _pipeline(db, a.id, "Воронка A")
    b_pipe = await _pipeline(db, b.id, "Воронка B")

    a_co = await _company(db, a.id, "Компания A")
    b_co = await _company(db, b.id, "Компания B")

    a_lead = await _lead(db, a.id, name="Лид A", owner_id=a_user.id,
                         pipeline=a_pipe, company_id=a_co.id)
    b_lead = await _lead(db, b.id, name="Лид B", owner_id=b_user.id,
                         pipeline=b_pipe, company_id=b_co.id)

    await _contact(db, a.id, a_lead.id, "ЛПР A")
    await _contact(db, b.id, b_lead.id, "ЛПР B")
    await db.commit()

    token_a = await issue_key(db, a.id)
    return {
        "a": a, "b": b, "a_user": a_user, "b_user": b_user,
        "a_pipe": a_pipe, "b_pipe": b_pipe, "a_co": a_co, "b_co": b_co,
        "a_lead": a_lead, "b_lead": b_lead, "token_a": token_a,
    }


# ---------------------------------------------------------------------------
# Разрешённый контроль — без него отказы ничего не значат
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_own_key_really_reads_its_workspace(db, two_workspaces):
    s = two_workspaces
    r = await ext(db, s["token_a"], f"/external/v1/leads/{s['a_lead'].id}")
    assert r.status_code == 200, r.text
    assert r.json()["company_name"] == "Лид A"

    r = await ext(db, s["token_a"], f"/external/v1/leads/{s['a_lead'].id}/summary")
    assert r.status_code == 200, r.text
    assert [c["name"] for c in r.json()["contacts"]] == ["ЛПР A"]

    r = await ext(db, s["token_a"], f"/external/v1/companies/{s['a_co'].id}")
    assert r.status_code == 200 and r.json()["name"] == "Компания A"

    r = await ext(db, s["token_a"], f"/external/v1/pipelines/{s['a_pipe'][0].id}/summary")
    assert r.status_code == 200
    assert r.json()["total_leads"] == 1


# ---------------------------------------------------------------------------
# Изоляция пространств
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_list_leads_shows_only_own_workspace(db, two_workspaces):
    s = two_workspaces
    r = await ext(db, s["token_a"], "/external/v1/leads?limit=100")
    assert r.status_code == 200
    names = [i["company_name"] for i in r.json()["items"]]
    assert names == ["Лид A"]
    assert "Лид B" not in r.text


@skip_no_pg
@pytest.mark.asyncio
async def test_foreign_child_ids_are_not_readable(db, two_workspaces):
    """Список и запрос по UUID — одна модель scope."""
    s = two_workspaces
    for path in (
        f"/external/v1/leads/{s['b_lead'].id}",
        f"/external/v1/leads/{s['b_lead'].id}/summary",
        f"/external/v1/companies/{s['b_co'].id}",
        f"/external/v1/pipelines/{s['b_pipe'][0].id}/summary",
    ):
        r = await ext(db, s["token_a"], path)
        assert r.status_code == 404, f"{path} → {r.status_code}: {r.text[:200]}"
        assert "Лид B" not in r.text and "Компания B" not in r.text


@skip_no_pg
@pytest.mark.asyncio
async def test_foreign_contacts_are_empty_not_leaked(db, two_workspaces):
    s = two_workspaces
    r = await ext(db, s["token_a"], f"/external/v1/contacts?lead_id={s['b_lead'].id}")
    assert r.status_code == 200
    assert r.json() == []

    r = await ext(db, s["token_a"], f"/external/v1/contacts?company_id={s['b_co'].id}")
    assert r.status_code == 200
    assert r.json() == []


@skip_no_pg
@pytest.mark.asyncio
async def test_filters_cannot_widen_the_selection(db, two_workspaces):
    """Фильтр по чужому исполнителю/воронке/этапу не расширяет выборку."""
    s = two_workspaces
    for path in (
        f"/external/v1/leads?assigned_to={s['b_user'].id}",
        f"/external/v1/leads?pipeline_id={s['b_pipe'][0].id}",
        f"/external/v1/leads?stage_id={s['b_pipe'][1].id}",
        "/external/v1/leads?q=Лид",
    ):
        r = await ext(db, s["token_a"], path)
        assert r.status_code == 200, path
        assert "Лид B" not in r.text, path


@skip_no_pg
@pytest.mark.asyncio
async def test_meta_and_pipelines_list_only_own(db, two_workspaces):
    s = two_workspaces
    r = await ext(db, s["token_a"], "/external/v1/meta")
    assert r.status_code == 200
    body = r.json()
    assert [m["name"] for m in body["managers"]] == ["Anna"]

    r = await ext(db, s["token_a"], "/external/v1/pipelines")
    assert r.status_code == 200
    assert [p["name"] for p in r.json()] == ["Воронка A"]


@skip_no_pg
@pytest.mark.asyncio
async def test_cursor_from_another_workspace_does_not_widen(db, two_workspaces):
    """Курсор — это только позиция сортировки, не право на выборку."""
    from app.external.repositories import encode_cursor

    s = two_workspaces
    stolen = encode_cursor(s["b_lead"].updated_at, s["b_lead"].id)
    r = await ext(db, s["token_a"], f"/external/v1/leads?cursor={stolen}")
    assert r.status_code == 200
    assert "Лид B" not in r.text


# ---------------------------------------------------------------------------
# Сам ключ
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_no_key_invalid_key_and_revoked_key_are_refused(db, two_workspaces):
    s = two_workspaces
    path = f"/external/v1/leads/{s['a_lead'].id}"

    assert (await ext(db, None, path)).status_code == 401
    assert (await ext(db, "drinkx_os_not-a-real-key", path)).status_code == 401
    assert (await ext(db, "", path)).status_code == 401

    revoked = await issue_key(db, s["a"].id, revoked=True)
    r = await ext(db, revoked, path)
    assert r.status_code == 403, r.text
    assert "Лид A" not in r.text

    wrong_scope = await issue_key(db, s["a"].id, scopes=("read:nothing",))
    r = await ext(db, wrong_scope, path)
    assert r.status_code == 403
    assert "Лид A" not in r.text


@skip_no_pg
@pytest.mark.asyncio
async def test_key_of_workspace_b_reads_b_and_only_b(db, two_workspaces):
    """Симметрия: ключ B видит своё и не видит A."""
    s = two_workspaces
    token_b = await issue_key(db, s["b"].id)
    r = await ext(db, token_b, "/external/v1/leads?limit=100")
    assert r.status_code == 200
    assert [i["company_name"] for i in r.json()["items"]] == ["Лид B"]
    r = await ext(db, token_b, f"/external/v1/leads/{s['a_lead'].id}")
    assert r.status_code == 404


@skip_no_pg
@pytest.mark.asyncio
async def test_secret_is_never_echoed_back(db, two_workspaces):
    """Ни один ответ не содержит ни токена, ни его хэша."""
    from app.external import keys

    s = two_workspaces
    token = s["token_a"]
    digest = keys.hash_key(token)
    for path in (
        "/external/v1/meta",
        "/external/v1/leads?limit=100",
        f"/external/v1/leads/{s['a_lead'].id}",
        f"/external/v1/leads/{s['a_lead'].id}/summary",
    ):
        r = await ext(db, token, path)
        assert token not in r.text, path
        assert digest not in r.text, path
        assert "drinkx_os_" not in r.text, path


@skip_no_pg
@pytest.mark.asyncio
async def test_rate_limit_refuses_the_eleventh_call_in_a_window(db, two_workspaces, monkeypatch):
    """Ограничение частоты на ключ действительно срабатывает.

    Redis в разведочном прогоне недоступен намеренно — так проверяется
    именно запасной счётчик в процессе, а не сеть.
    """
    from app.external import dependencies as dep

    s = two_workspaces
    token = await issue_key(db, s["a"].id)

    def _no_redis():
        raise RuntimeError("redis disabled for this test")

    monkeypatch.setattr(dep, "_get_rl_redis", _no_redis)
    dep._rate_state.clear()

    path = "/external/v1/meta"
    codes = []
    for _ in range(30):
        codes.append((await ext(db, token, path)).status_code)
        if codes[-1] == 429:
            break
    assert codes[:10] == [200] * 10, codes
    assert codes[-1] == 429, codes
    # Запасной счётчик — это «ведро» на 10 запросов, которое доливается на
    # 10 в секунду. Поэтому отказ приходит не строго на 11-м вызове, а как
    # только серия обгоняет доливку. Фиксируем фактическое поведение.
    assert len(codes) <= 30, codes


# ---------------------------------------------------------------------------
# Форма поверхности
# ---------------------------------------------------------------------------

def test_external_surface_is_read_only_and_has_no_key_management():
    """Маршрутов выпуска/просмотра/отзыва ключей в HTTP нет вовсе."""
    from app.main import app

    external = [r for r in app.routes if getattr(r, "path", "").startswith("/external/")]
    assert external, "маршруты /external не зарегистрированы"
    for r in external:
        assert set(r.methods) <= {"GET", "HEAD", "OPTIONS"}, (r.path, r.methods)

    all_paths = " ".join(getattr(r, "path", "") for r in app.routes)
    for word in ("service-key", "service_key", "api-keys", "api_keys"):
        assert word not in all_paths, f"неожиданный маршрут управления ключами: {word}"


# ---------------------------------------------------------------------------
# Второй вход по тому же ключу: MCP
# ---------------------------------------------------------------------------
#
# У ключа интеграции две поверхности: REST `/external/v1/*` и MCP-сервер
# (`app/external/mcp_server.py`), где четыре инструмента читают тот же
# `Authorization` и сами разрешают его в пространство. Прежние тесты MCP
# проверяли только регистрацию инструментов и отказ без заголовка —
# изоляцию пространства через эту поверхность не проверял никто.
#
# Подменяются ровно две границы: источник заголовка (в тесте нет живого
# HTTP-запроса MCP) и фабрика сессий (нужна тестовая база). Разрешение
# ключа, проверка scope и сам запрос данных идут настоящие.


async def _mcp_call(db, tool, token: str | None, **kwargs):
    from app.external import mcp_server as mcp

    class _Ctx:
        async def __aenter__(self_c):
            return db

        async def __aexit__(self_c, *exc):
            return False

    orig_header = mcp._authorization_header
    orig_factory = mcp.get_session_factory
    mcp._authorization_header = lambda: (f"Bearer {token}" if token else None)
    # Код зовёт `get_session_factory()()`: сначала получает фабрику, потом
    # открывает сессию. Подменяем обе ступени.
    mcp.get_session_factory = lambda: (lambda: _Ctx())
    try:
        return await tool(**kwargs)
    finally:
        mcp._authorization_header = orig_header
        mcp.get_session_factory = orig_factory


@skip_no_pg
@pytest.mark.asyncio
async def test_mcp_tools_are_scoped_to_the_key_workspace(db, two_workspaces):
    """Ключ пространства A через MCP не видит данных B."""
    from app.external import mcp_server as mcp

    s = two_workspaces
    key_a = await issue_key(db, s["a"].id)

    found = await _mcp_call(db, mcp.search_leads, key_a, q="")
    names = {row.get("company_name") for row in found}
    assert names, "положительный контроль: ключ обязан что-то видеть"
    assert s["a_lead"].company_name in names
    assert s["b_lead"].company_name not in names

    mine = await _mcp_call(
        db, mcp.get_lead_summary, key_a, lead_id=str(s["a_lead"].id)
    )
    assert mine is not None

    theirs = await _mcp_call(
        db, mcp.get_lead_summary, key_a, lead_id=str(s["b_lead"].id)
    )
    assert theirs is None, "сводка по чужому лиду не должна отдаваться"


@skip_no_pg
@pytest.mark.asyncio
async def test_mcp_refuses_a_revoked_key_and_a_wrong_scope(db, two_workspaces):
    """Отзыв и scope действуют и на второй поверхности."""
    from fastapi import HTTPException

    from app.external import mcp_server as mcp

    s = two_workspaces
    revoked = await issue_key(db, s["a"].id, revoked=True)
    wrong_scope = await issue_key(db, s["a"].id, scopes=("read:nothing",))

    for token, label in ((None, "без ключа"), (revoked, "отозванный"),
                         ("drinkx_os_нет-такого", "неизвестный"),
                         (wrong_scope, "чужой scope")):
        with pytest.raises(HTTPException) as exc:
            await _mcp_call(db, mcp.search_leads, token, q="")
        assert exc.value.status_code in (401, 403), (label, exc.value.status_code)
