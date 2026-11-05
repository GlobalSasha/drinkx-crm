"""@-упоминания в комментариях к лиду.

Кого упомянули, сервер определяет сам по тексту: так упоминание работает и
из списка подсказок, и если имя набрали руками, и если текст поправили.
Правило разбора повторено в `apps/web/lib/mentions.ts` для подсветки.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def find_mentions(text: str | None, users: Iterable) -> list:
    """Вернуть пользователей, чьё `@Имя` встречается в тексте.

    Длинные имена проверяются первыми, поэтому «@Анна Мария» не заденет
    просто «Анну». Почта вроде `a@anton.ru` упоминанием не считается.
    """
    by_name: dict[str, list] = {}
    for user in users:
        name = (user.name or "").strip()
        if name:
            by_name.setdefault(name.casefold(), []).append(user)
    if not text or not by_name:
        return []

    names = sorted(by_name, key=len, reverse=True)
    pattern = re.compile(
        r"(?<![\w@])@(" + "|".join(re.escape(n) for n in names) + r")(?!\w)",
        re.IGNORECASE,
    )
    found: dict = {}
    for match in pattern.finditer(text):
        for user in by_name.get(match.group(1).casefold(), []):
            found[user.id] = user
    return list(found.values())


async def notify_mentions(
    db: AsyncSession,
    *,
    lead,
    actor,
    text: str,
    previous_text: str | None = None,
) -> None:
    """Сообщить упомянутым. При правке текста пишем только тем, кого в нём
    раньше не было, и никогда не пишем автору."""
    from app.auth.models import User
    from app.leads.access import may_access_lead
    from app.notifications.services import safe_notify

    users = (
        await db.execute(select(User).where(User.workspace_id == lead.workspace_id))
    ).scalars().all()
    already = {u.id for u in find_mentions(previous_text, users)}

    for user in find_mentions(text, users):
        if user.id == actor.id or user.id in already:
            continue
        await safe_notify(
            db,
            workspace_id=lead.workspace_id,
            user_id=user.id,
            kind="mention",
            title=f"Вас упомянули · {lead.company_name}",
            body=f"{actor.name}: {text}"[:400],
            # Менеджеру чужой лид не открыть: ссылка привела бы на «не найдено»,
            # поэтому такому получателю приходит только текст вопроса.
            lead_id=lead.id if may_access_lead(user, lead) else None,
        )
