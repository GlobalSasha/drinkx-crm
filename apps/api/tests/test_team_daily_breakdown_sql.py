"""Regression guard: daily_breakdown's raw SQL must bind exactly its 4 params.

The query previously used `:wid::uuid` etc. The double-colon cast form makes
SQLAlchemy mis-parse the bind-param name (drops its last char → `wi`, `ui`,
`from`, `t`), so the values passed in `db.execute(sql, {...})` never bind and
the query 500s at execution. Use CAST(:x AS type) instead. This test fails if
anyone reintroduces the `::` form next to a bind param in daily_breakdown.
"""
from __future__ import annotations

import re

from sqlalchemy import text


def _daily_breakdown_sql() -> str:
    src = open("app/team/repositories.py", encoding="utf-8").read()
    m = re.search(
        r"async def daily_breakdown.*?sql = text\(\"\"\"(.*?)\"\"\"\)", src, re.S
    )
    assert m, "could not locate daily_breakdown's text() SQL"
    return m.group(1)


def test_daily_breakdown_binds_exactly_its_four_params():
    t = text(_daily_breakdown_sql())
    assert sorted(t._bindparams.keys()) == ["from_", "to", "uid", "wid"]
