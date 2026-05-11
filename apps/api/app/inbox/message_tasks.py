"""Async cores for inbox-side Celery tasks — Sprint 3.4.

G4b — `transcribe_call_async` downloads the call recording, runs STT
via the configured `SttProvider`, summarizes the transcript with MiMo
Flash, and writes everything back onto the `inbox_messages` row. On
matched calls it also schedules a Lead Agent refresh 60s later so the
suggestion picks up the new context.

The function is deliberately resilient: any single step that fails
(audio download, STT, summary) leaves the InboxMessage row with the
fields it managed to fill in. We never re-raise — Celery retries are
expensive for a UX polish.
"""
from __future__ import annotations

from uuid import UUID

import httpx
import structlog
from sqlalchemy import select

from app.activity.models import Activity
from app.inbox.models import InboxMessage
from app.inbox.stt.base import SttError
from app.inbox.stt.factory import get_stt_provider

log = structlog.get_logger()


_SUMMARY_SYSTEM = (
    "Ты ассистент менеджера DrinkX. Тебе дают транскрипт телефонного "
    "разговора менеджера с клиентом B2B-сегмента (кофейные станции). "
    "Пиши кратко и по делу, без воды."
)

_SUMMARY_TEMPLATE = (
    "Ниже транскрипт телефонного разговора менеджера с клиентом DrinkX. "
    "Напиши резюме в 2-3 предложениях: цель звонка, что спросил клиент, "
    "о чём договорились, следующий шаг.\n\n"
    "Транскрипт:\n{transcript}"
)


async def transcribe_call_async(message_id: UUID) -> dict:
    """G4b — STT + summary pipeline. See module docstring."""
    from app.scheduled.jobs import _build_task_engine_and_factory

    engine, factory = _build_task_engine_and_factory()
    try:
        async with factory() as session:
            res = await session.execute(
                select(InboxMessage).where(InboxMessage.id == message_id)
            )
            msg = res.scalar_one_or_none()
            if msg is None:
                return {
                    "job": "transcribe_call",
                    "status": "message_not_found",
                    "message_id": str(message_id),
                }
            if msg.channel != "phone":
                return {
                    "job": "transcribe_call",
                    "status": "wrong_channel",
                    "channel": msg.channel,
                }
            if msg.call_status == "missed" or not msg.media_url:
                return {
                    "job": "transcribe_call",
                    "status": "nothing_to_transcribe",
                }

            # ----------------------------------------------------------
            # 1. Download the recording.
            # ----------------------------------------------------------
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    audio_resp = await client.get(msg.media_url)
                if audio_resp.status_code != 200:
                    log.warning(
                        "inbox.transcribe.audio_bad_status",
                        status=audio_resp.status_code,
                        message_id=str(message_id),
                    )
                    return {
                        "job": "transcribe_call",
                        "status": f"audio_status_{audio_resp.status_code}",
                    }
                audio_bytes = audio_resp.content
            except httpx.HTTPError as exc:
                log.warning(
                    "inbox.transcribe.audio_http_error",
                    error=str(exc)[:200],
                    message_id=str(message_id),
                )
                return {
                    "job": "transcribe_call",
                    "status": "audio_http_error",
                }

            # ----------------------------------------------------------
            # 2. STT.
            # ----------------------------------------------------------
            stt = get_stt_provider()
            try:
                transcript = await stt.transcribe(audio_bytes, "ru")
            except SttError as exc:
                log.warning(
                    "inbox.transcribe.stt_failed",
                    provider=stt.provider_name,
                    error=str(exc)[:200],
                    message_id=str(message_id),
                )
                # Provider failure — record the attempt so we don't loop
                # on the same row forever, but leave transcript blank.
                msg.stt_provider = stt.provider_name
                await session.commit()
                return {
                    "job": "transcribe_call",
                    "status": f"stt_failed:{exc}",
                }

            if not transcript:
                msg.stt_provider = stt.provider_name
                await session.commit()
                return {
                    "job": "transcribe_call",
                    "status": "empty_transcript",
                }

            # ----------------------------------------------------------
            # 3. Summary via MiMo Flash (prefilter task type).
            # ----------------------------------------------------------
            from app.enrichment.providers.base import TaskType
            from app.enrichment.providers.factory import complete_with_fallback

            summary = ""
            try:
                completion = await complete_with_fallback(
                    system=_SUMMARY_SYSTEM,
                    user=_SUMMARY_TEMPLATE.format(transcript=transcript[:3000]),
                    task_type=TaskType.prefilter,
                    max_tokens=200,
                    temperature=0.3,
                    timeout_seconds=30.0,
                )
                summary = (completion.text or "").strip()
            except Exception as exc:  # noqa: BLE001 — LLM down must not lose transcript
                log.warning(
                    "inbox.transcribe.summary_failed",
                    error=str(exc)[:200],
                    message_id=str(message_id),
                )

            # ----------------------------------------------------------
            # 4. Persist transcript / summary / provider.
            # ----------------------------------------------------------
            msg.transcript = transcript
            msg.summary = summary or None
            msg.stt_provider = stt.provider_name

            # 5. Best-effort: refresh the lead-card Activity body so the
            #    feed shows the summary instead of "Звонок 4:12". We
            #    locate the matching Activity by lead + by the
            #    inbox_message_id stamp dropped in payload_json at
            #    receive() time. Skipped silently if unmatched / not
            #    found — the call still shows duration in the UI.
            if msg.lead_id and summary:
                act_res = await session.execute(
                    select(Activity)
                    .where(Activity.lead_id == msg.lead_id)
                    .where(Activity.type == "phone")
                )
                for act in act_res.scalars():
                    if (
                        isinstance(act.payload_json, dict)
                        and act.payload_json.get("inbox_message_id") == str(msg.id)
                    ):
                        dur = msg.call_duration or 0
                        mins, secs = divmod(dur, 60)
                        act.body = f"📞 Звонок {mins}:{secs:02d} · {summary}"
                        break

            await session.commit()

            # 6. Trigger Lead Agent refresh now that we have context.
            if msg.lead_id:
                try:
                    from app.scheduled.jobs import lead_agent_refresh_suggestion

                    lead_agent_refresh_suggestion.apply_async(
                        args=[str(msg.lead_id)],
                        countdown=60,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "inbox.transcribe.lead_agent_kick_failed",
                        error=str(exc)[:200],
                        lead_id=str(msg.lead_id),
                    )

            log.info(
                "inbox.transcribe.ok",
                provider=stt.provider_name,
                message_id=str(message_id),
                transcript_chars=len(transcript),
                summary_chars=len(summary),
            )
            return {
                "job": "transcribe_call",
                "status": "ok",
                "provider": stt.provider_name,
                "transcript_chars": len(transcript),
                "summary_chars": len(summary),
            }
    finally:
        await engine.dispose()
