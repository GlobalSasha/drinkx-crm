"""Logs REST — admin-only read of recent application logs.

Reads back the rotating JSON log files (api / worker / beat) so an operator —
or an agent over HTTPS — can triage errors without SSH:

    GET /admin/logs?level=error&since=2h
    GET /admin/logs?service=worker&contains=Traceback
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import require_admin
from app.auth.models import User
from app.logs import service as svc

router = APIRouter(prefix="/admin/logs", tags=["logs"])


@router.get("")
async def get_logs(
    level: str = Query("all", description="all | info | warning | error"),
    since: str = Query("1h", description="window, e.g. 30m, 2h, 1d"),
    service: str | None = Query(None, description="api | worker | beat"),
    contains: str | None = Query(None, description="substring filter"),
    limit: int = Query(200, ge=1, le=2000),
    _user: Annotated[User, Depends(require_admin)] = ...,
) -> dict[str, Any]:
    """Recent application logs, newest last. Admin-only. For quick triage:
    `?level=error` shows just errors/tracebacks of the last hour."""
    return svc.read_logs(
        level=level,
        since=since,
        service=service,
        contains=contains,
        limit=limit,
    )
