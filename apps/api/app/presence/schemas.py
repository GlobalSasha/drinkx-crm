from __future__ import annotations

from pydantic import BaseModel


class PingOut(BaseModel):
    ok: bool
