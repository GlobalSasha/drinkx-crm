"""SEC-05 — разведка: загрузка, хранение и выдача файлов.

Фактические пути (см. `app/activity/files_router.py`):

    POST   /leads/{lead_id}/files                    — вложение в ленту лида
    POST   /leads/{lead_id}/tasks/{task_id}/files    — вложение к задаче
    GET    /leads/{lead_id}/tasks/{task_id}/files    — список
    GET    /activities/{activity_id}/download        — подписанная ссылка
    DELETE /activities/{activity_id}/file            — удаление

Право на файл — это право на лид: у всех пяти маршрутов на роутере стоят
`lead_access_guard` и `activity_file_access_guard`. Ключ в хранилище
собирается сервером из UUID: `{ws}/{lead}/{activity}/{безопасное имя}`.

Проверяется: что действительно пишется и читается разрешённым актором,
что запрещённому не достаётся ни файл, ни подписанная ссылка, ни удаление,
и что опасное имя не выводит ключ за свой каталог.

Хранилище заменено записывающей заглушкой — ни одного сетевого вызова.
Загрузка импорта и `base_update` разобраны в SEC-06 и SEC-04.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401 — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64


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


async def _lead(db, workspace_id, owner_id, name="Компания"):
    from app.leads import repositories as repo

    return await repo.create_lead(
        db, workspace_id, dict(company_name=name),
        assigned_to=owner_id, assignment_status="assigned",
    )


class FakeStorage:
    """Заглушка хранилища: запоминает вызовы, ничего не отправляет."""

    def __init__(self):
        self.uploaded: list[tuple[str, int, str]] = []
        self.signed: list[tuple[str, int]] = []
        self.deleted: list[str] = []

    async def upload(self, *, key, content, content_type):
        self.uploaded.append((key, len(content), content_type))

    async def create_signed_url(self, *, key, expires_in=300):
        self.signed.append((key, expires_in))
        return f"https://storage.invalid/signed/{key}?exp={expires_in}"

    async def delete(self, *, key):
        self.deleted.append(key)


@pytest.fixture
def storage(monkeypatch):
    from app.activity import files as files_mod
    from app.scheduled.celery_app import celery_app

    fake = FakeStorage()
    monkeypatch.setattr(files_mod, "get_storage_client", lambda: fake)
    monkeypatch.setattr(celery_app, "send_task", lambda *a, **kw: None)
    return fake


async def call(db, actor, method, path, files=None, raise_errors=True):
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=raise_errors)
        async with AsyncClient(transport=transport, base_url="http://test") as cl:
            kwargs = {"files": files} if files is not None else {}
            return await cl.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


async def upload(db, actor, lead_id, filename, content=PNG):
    return await call(
        db, actor, "POST", f"/leads/{lead_id}/files",
        files={"file": (filename, content, "application/octet-stream")},
    )



async def _task(db, workspace_id, lead_id, user_id, title="Позвонить"):
    """Настоящая задача этого лида — задачи хранятся как Activity(type=task)."""
    from app.activity.models import Activity, ActivityType

    task = Activity(
        lead_id=lead_id,
        user_id=user_id,
        type=ActivityType.task.value,
        body=title,
        payload_json={"title": title},
    )
    if hasattr(Activity, "workspace_id"):
        task.workspace_id = workspace_id
    db.add(task)
    await db.flush()
    return task


async def _file_url_from_a_fresh_session(activity_id):
    """Перечитать ключ отдельной сессией — не той, в которой шла загрузка.

    Иначе значение может прийти из карты идентичности и проверка будет
    ничего не стоить.
    """
    from sqlalchemy import select

    from app.activity.models import Activity
    from tests.conftest import _test_session_factory

    async with _test_session_factory() as fresh:
        return (
            await fresh.execute(select(Activity.file_url).where(Activity.id == activity_id))
        ).scalar_one()


async def attach_file(db, workspace_id, lead_id, user_id, filename="dogovor.png"):
    """Готовое вложение с заполненным ключом.

    Короткий путь для проверок доступа: они про то, кому достаётся файл,
    а не про то, как он загружается. Сама загрузка и сохранение ключа
    проверяются отдельно, через настоящий HTTP POST.
    """
    from app.activity.models import Activity, ActivityType
    from app.storage.paths import build_object_key

    activity = Activity(
        lead_id=lead_id,
        user_id=user_id,
        type=ActivityType.file.value,
        file_kind="image",
        payload_json={"file_name": filename, "file_size": len(PNG), "source": "lead_file_upload"},
    )
    if hasattr(Activity, "workspace_id"):
        activity.workspace_id = workspace_id
    db.add(activity)
    await db.flush()
    activity.file_url = build_object_key(
        workspace_id=workspace_id, lead_id=lead_id,
        activity_id=activity.id, filename=filename,
    )
    await db.commit()
    return activity


@pytest.fixture
async def scene(db):
    a = await _workspace(db, "Пространство A")
    b = await _workspace(db, "Пространство B")
    owner = await _user(db, a.id, "Owner")
    stranger = await _user(db, a.id, "Stranger")
    head = await _user(db, a.id, "Head", "head")
    outsider = await _user(db, b.id, "Outsider", "admin")
    lead = await _lead(db, a.id, owner.id, "Лид владельца")
    await db.commit()
    return dict(a=a, b=b, owner=owner, stranger=stranger, head=head,
                outsider=outsider, lead=lead)


# ===========================================================================
# Разрешённый контроль
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_owner_upload_writes_the_object_under_its_own_folder(db, scene, storage):
    """Разрешённый контроль записи: владелец действительно грузит файл."""
    from sqlalchemy import select

    from app.activity.models import Activity

    s = scene
    r = await upload(db, s["owner"], s["lead"].id, "договор.png")
    assert r.status_code == 201, r.text
    activity_id = uuid.UUID(r.json()["id"])
    assert r.json()["file_name"] == "договор.png"

    key, size, ctype = storage.uploaded[-1]
    assert key == f"{s['a'].id}/{s['lead'].id}/{activity_id}/dogovor.png"
    assert size == len(PNG) and ctype == "image/png"

    row = (
        await db.execute(select(Activity).where(Activity.id == activity_id))
    ).scalar_one()
    assert row.lead_id == s["lead"].id


@skip_no_pg
@pytest.mark.asyncio
@pytest.mark.parametrize("path_kind", ["lead-file", "task-file"])
async def test_upload_persists_the_storage_key_on_both_paths(db, scene, storage, path_kind):
    """Регрессия SEC-05-1: ключ хранилища доходит до базы на обоих путях.

    Было: `upload_lead_file` присваивал `file_url` уже после `flush`, а
    следом `db.refresh(activity)` перечитывал строку и отбрасывал
    неотправленное присваивание. В базе оставался NULL: объект в
    хранилище есть, скачать нельзя (500), удаление сносило строку и
    оставляло сироту. `upload_task_file` — тонкая обёртка над тем же
    сервисом, поэтому проверяются оба маршрута.

    Проверяется не код ответа, а состояние базы: ключ перечитывается
    ОТДЕЛЬНОЙ сессией, затем подписанная ссылка и удаление должны
    обратиться ровно к тому ключу, который получило хранилище.

    Прежние тесты этого не ловили: там сессия подменена заглушкой, у
    которой `refresh` ничего не делает.
    """
    s = scene
    if path_kind == "lead-file":
        path = f"/leads/{s['lead'].id}/files"
        expected_parent = None
    else:
        task = await _task(db, s["a"].id, s["lead"].id, s["owner"].id)
        await db.commit()
        path = f"/leads/{s['lead'].id}/tasks/{task.id}/files"
        expected_parent = str(task.id)

    r = await call(
        db, s["owner"], "POST", path,
        files={"file": ("договор.png", PNG, "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    activity_id = uuid.UUID(body["id"])
    assert body.get("parent_task_id") == expected_parent
    assert body["file_name"] == "договор.png"

    assert storage.uploaded, "объект в хранилище не записан"
    stored_key, size, ctype = storage.uploaded[-1]
    assert stored_key == f"{s['a'].id}/{s['lead'].id}/{activity_id}/dogovor.png"
    assert size == len(PNG) and ctype == "image/png"

    persisted = await _file_url_from_a_fresh_session(activity_id)
    assert persisted == stored_key, "ключ хранилища не сохранён в базе"

    r = await call(db, s["owner"], "GET", f"/activities/{activity_id}/download")
    assert r.status_code == 200, r.text
    assert storage.signed[-1] == (stored_key, 300)

    r = await call(db, s["owner"], "DELETE", f"/activities/{activity_id}/file")
    assert r.status_code == 204, r.text
    assert storage.deleted[-1] == stored_key
    assert await _row_exists(activity_id) is False


async def _row_exists(activity_id) -> bool:
    from sqlalchemy import select

    from app.activity.models import Activity
    from tests.conftest import _test_session_factory

    async with _test_session_factory() as fresh:
        row = (
            await fresh.execute(select(Activity.id).where(Activity.id == activity_id))
        ).scalar_one_or_none()
    return row is not None


@skip_no_pg
@pytest.mark.asyncio
@pytest.mark.parametrize("path_kind", ["lead-file", "task-file"])
async def test_storage_failure_leaves_no_attachment_behind(db, scene, storage, path_kind):
    """Сбой хранилища не оставляет сохранённого вложения.

    Дополнительный `flush` из исправления SEC-05-1 стоит ДО загрузки, и
    надо показать, что он не создаёт наполовину записанное вложение:
    транзакция ручки не коммитится, отдельная сессия строки не видит,
    подпись и удаление не запрашивались.
    """
    from app.storage.client import StorageError

    s = scene
    if path_kind == "lead-file":
        path = f"/leads/{s['lead'].id}/files"
    else:
        task = await _task(db, s["a"].id, s["lead"].id, s["owner"].id)
        await db.commit()
        path = f"/leads/{s['lead'].id}/tasks/{task.id}/files"

    async def _boom(*, key, content, content_type):
        storage.uploaded.append((key, len(content), content_type))
        raise StorageError("upload failed [500]: boom")

    storage.upload = _boom

    with pytest.raises(StorageError):
        await call(
            db, s["owner"], "POST", path,
            files={"file": ("договор.png", PNG, "application/octet-stream")},
        )

    attempted_key = storage.uploaded[-1][0]
    await db.rollback()
    assert await _file_url_by_key(attempted_key) is None, "вложение всё-таки сохранено"
    assert storage.signed == [] and storage.deleted == []


async def _file_url_by_key(key):
    """Есть ли в базе строка с таким ключом — читается отдельной сессией."""
    from sqlalchemy import select

    from app.activity.models import Activity
    from tests.conftest import _test_session_factory

    async with _test_session_factory() as fresh:
        return (
            await fresh.execute(select(Activity.id).where(Activity.file_url == key))
        ).scalar_one_or_none()


@skip_no_pg
@pytest.mark.asyncio
async def test_owner_downloads_and_deletes_a_file_with_a_key(db, scene, storage):
    """Разрешённый контроль чтения и удаления — на вложении с ключом."""
    from sqlalchemy import select

    from app.activity.models import Activity

    s = scene
    activity = await attach_file(db, s["a"].id, s["lead"].id, s["owner"].id)
    key = activity.file_url

    r = await call(db, s["owner"], "GET", f"/activities/{activity.id}/download")
    assert r.status_code == 200, r.text
    assert r.json()["expires_in"] == 300
    assert storage.signed[-1] == (key, 300)

    r = await call(db, s["owner"], "DELETE", f"/activities/{activity.id}/file")
    assert r.status_code == 204
    assert storage.deleted == [key]
    assert (
        await db.execute(select(Activity).where(Activity.id == activity.id))
    ).scalar_one_or_none() is None


# ===========================================================================
# Запрещённый актор
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_stranger_and_other_workspace_cannot_upload(db, scene, storage):
    from sqlalchemy import func, select

    from app.activity.models import Activity

    s = scene
    before = (
        await db.execute(
            select(func.count()).select_from(Activity).where(Activity.lead_id == s["lead"].id)
        )
    ).scalar_one()

    for actor in (s["stranger"], s["outsider"]):
        r = await upload(db, actor, s["lead"].id, "чужой.png")
        assert r.status_code in (403, 404), (actor.name, r.status_code, r.text[:200])

    assert storage.uploaded == []
    after = (
        await db.execute(
            select(func.count()).select_from(Activity).where(Activity.lead_id == s["lead"].id)
        )
    ).scalar_one()
    assert after == before


@skip_no_pg
@pytest.mark.asyncio
async def test_stranger_gets_neither_the_file_nor_a_signed_link(db, scene, storage):
    from sqlalchemy import select

    from app.activity.models import Activity

    s = scene
    activity = await attach_file(db, s["a"].id, s["lead"].id, s["owner"].id)
    activity_id = activity.id
    storage.signed.clear()
    storage.deleted.clear()

    for actor in (s["stranger"], s["outsider"]):
        r = await call(db, actor, "GET", f"/activities/{activity_id}/download")
        assert r.status_code in (403, 404), (actor.name, r.status_code)
        assert "https://storage.invalid" not in r.text

        r = await call(db, actor, "DELETE", f"/activities/{activity_id}/file")
        assert r.status_code in (403, 404), (actor.name, r.status_code)

    assert storage.signed == [], "подписанная ссылка выдана запрещённому актору"
    assert storage.deleted == [], "запрещённый актор удалил объект в хранилище"
    assert (
        await db.execute(select(Activity).where(Activity.id == activity_id))
    ).scalar_one_or_none() is not None


@skip_no_pg
@pytest.mark.asyncio
async def test_head_of_the_same_workspace_may_read(db, scene, storage):
    """Разрешённый контроль для политики: руководителю лид доступен."""
    s = scene
    activity = await attach_file(db, s["a"].id, s["lead"].id, s["owner"].id)

    r = await call(db, s["head"], "GET", f"/activities/{activity.id}/download")
    assert r.status_code == 200, r.text


# ===========================================================================
# Имя файла и ключ в хранилище
# ===========================================================================

@pytest.mark.parametrize(
    "raw",
    [
        "../../../etc/passwd.png",
        "/absolute/path/file.png",
        "..\\..\\windows\\system32\\evil.png",
        "%2e%2e%2fsecret.png",
        "файл с пробелами.PNG",
        "....//....//x.png",
        "a" * 400 + ".png",
        ".png",
        "....png",
    ],
)
def test_slug_never_escapes_its_folder(raw):
    from app.storage.paths import slug_filename

    slug = slug_filename(raw)
    assert "/" not in slug and "\\" not in slug
    assert ".." not in slug
    assert not slug.startswith(".")
    assert slug == slug.strip()


@skip_no_pg
@pytest.mark.asyncio
async def test_dangerous_names_stay_inside_the_lead_folder(db, scene, storage):
    s = scene
    for raw in ("../../../etc/passwd.png", "/absolute/evil.png", "..\\..\\x.png"):
        r = await upload(db, s["owner"], s["lead"].id, raw)
        assert r.status_code == 201, (raw, r.status_code, r.text[:200])
        key = storage.uploaded[-1][0]
        parts = key.split("/")
        assert len(parts) == 4, (raw, key)
        assert parts[0] == str(s["a"].id) and parts[1] == str(s["lead"].id)
        assert ".." not in key and not key.startswith("/")


@skip_no_pg
@pytest.mark.asyncio
async def test_identical_names_do_not_overwrite_each_other(db, scene, storage):
    """Ключ включает UUID записи, поэтому одинаковые имена не сталкиваются."""
    s = scene
    await upload(db, s["owner"], s["lead"].id, "акт.png")
    await upload(db, s["owner"], s["lead"].id, "акт.png")
    first, second = storage.uploaded[-2][0], storage.uploaded[-1][0]
    assert first != second
    assert first.rsplit("/", 1)[1] == second.rsplit("/", 1)[1] == "akt.png"


# ===========================================================================
# Тип содержимого и размер
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename,content",
    [
        ("payload.exe", b"MZ" + b"0" * 64),
        ("payload.svg", b"<svg onload=alert(1)>"),
        ("payload.html", b"<html><script>alert(1)</script></html>"),
        ("payload.php", b"<?php system($_GET['c']); ?>"),
        ("payload", PNG),                      # без расширения
        ("invoice.pdf.exe", PDF),              # внешнее расширение решает
        ("picture.png", PDF),                  # подпись не совпадает с .png
        ("scan.pdf", PNG),                     # и наоборот
    ],
)
async def test_unsupported_or_mismatched_content_is_refused(
    db, scene, storage, filename, content
):
    s = scene
    r = await upload(db, s["owner"], s["lead"].id, filename, content)
    assert r.status_code == 400, (filename, r.status_code, r.text[:200])
    assert storage.uploaded == [], filename


@skip_no_pg
@pytest.mark.asyncio
async def test_text_types_pass_without_a_binary_signature(db, scene, storage):
    """Разрешённый контроль к проверке выше: .csv действительно принимается."""
    s = scene
    r = await upload(db, s["owner"], s["lead"].id, "выгрузка.csv", "имя;телефон\n".encode())
    assert r.status_code == 201, r.text
    assert storage.uploaded[-1][0].endswith("vygruzka.csv")


@skip_no_pg
@pytest.mark.asyncio
async def test_size_limit_applies_before_storage(db, scene, storage, monkeypatch):
    """Предел моделируется маленьким значением, а не настоящими 25 МБ."""
    from app.activity import files as files_mod

    s = scene
    monkeypatch.setattr(files_mod, "MAX_FILE_BYTES", 1024)
    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * 4096
    r = await upload(db, s["owner"], s["lead"].id, "big.png", oversized)
    assert r.status_code == 413, r.status_code
    assert storage.uploaded == []

    r = await upload(db, s["owner"], s["lead"].id, "empty.png", b"")
    assert r.status_code == 400
    assert storage.uploaded == []


# ===========================================================================
# Родительская задача
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_parent_task_must_belong_to_the_lead(db, scene, storage):
    """Регрессия SEC-05-2: `task_id` сверяется с лидом из пути.

    Было: принимался любой UUID. Право даёт лид, поэтому чужих данных
    это не затрагивало — файл оседал в каталоге своего лида, — но
    привязка шла к несуществующей или чужой задаче.

    Стало: 404 на неизвестную задачу и на задачу другого лида; ничего не
    записано в базу и не отправлено в хранилище. Разрешённый контроль —
    настоящая задача этого лида — проходит.
    """
    from sqlalchemy import func, select

    from app.activity.models import Activity

    s = scene
    other_lead = await _lead(db, s["a"].id, s["owner"].id, "Другой лид")
    task_here = await _task(db, s["a"].id, s["lead"].id, s["owner"].id)
    task_elsewhere = await _task(db, s["a"].id, other_lead.id, s["owner"].id)
    await db.commit()

    before = (await db.execute(select(func.count(Activity.id)))).scalar_one()

    for bad in (uuid.uuid4(), task_elsewhere.id):
        r = await call(
            db, s["owner"], "POST",
            f"/leads/{s['lead'].id}/tasks/{bad}/files",
            files={"file": ("акт.png", PNG, "application/octet-stream")},
            raise_errors=False,
        )
        assert r.status_code == 404, (bad, r.status_code)

    assert storage.uploaded == [], "в хранилище всё-таки записано"
    after = (await db.execute(select(func.count(Activity.id)))).scalar_one()
    assert after == before, "в базе появилась строка"

    # Список файлов той же задачи закрыт по тому же правилу.
    r = await call(db, s["owner"], "GET",
                   f"/leads/{s['lead'].id}/tasks/{task_elsewhere.id}/files",
                   raise_errors=False)
    assert r.status_code == 404, r.status_code

    # Разрешённый контроль: своя задача — файл записан и виден в списке.
    r = await call(
        db, s["owner"], "POST",
        f"/leads/{s['lead'].id}/tasks/{task_here.id}/files",
        files={"file": ("акт.png", PNG, "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["parent_task_id"] == str(task_here.id)
    assert storage.uploaded[-1][0].startswith(f"{s['a'].id}/{s['lead'].id}/")

    r = await call(db, s["owner"], "GET",
                   f"/leads/{s['lead'].id}/tasks/{task_here.id}/files")
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()] != []

