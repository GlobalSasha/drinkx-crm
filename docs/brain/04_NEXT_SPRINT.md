# Sprint 3.4 — Unified Inbox: Telegram · MAX · Телефония

**Статус:** 📋 SPEC (не начат)
**После:** Sprint 3.3 Companies + Global Search ✅
**Следующая свободная миграция:** **0025** (последняя в проде — `0024_contacts_workspace_id_not_null`)

---

## Контекст: что уже есть

Sprint 2.0 реализовал Gmail-интеграцию — пакет `app/inbox/` **уже существует в продакшне**:

| Компонент | Статус |
|---|---|
| `app/inbox/` пакет | ✅ live |
| `channel_connections` (migration 0008) | ✅ live |
| `inbox_items` (migration 0009) | ✅ live |
| Gmail sync (read-only, Celery 5 min) | ✅ live |
| `/inbox` страница с AI-саджестами | ✅ live |
| Email-активности в ленте лида | ✅ live |
| **Gmail send** (отправка из CRM) | ⏸ не сделано |

Gmail — **уже 1-й канал**. Sprint 3.4 добавляет каналы 2, 3, 4.

---

## Бизнес-цель

Менеджер видит в карточке лида всю переписку — Gmail, Telegram, MAX, звонки —
и отвечает/звонит, не выходя из CRM.

---

## ADR-023 — Расширение inbox: messenger-каналы отдельной таблицей

```
Проблема:  inbox_items заточена под Gmail (gmail_message_id UNIQUE, triage-логика,
           AI-suggestion chips). Telegram/MAX — это real-time чат, не email-очередь.
Решение:   новая таблица inbox_messages для мессенджер-каналов и телефонии.
           app/inbox/ расширяется адаптерами без переписывания.
           Gmail остаётся на inbox_items; новые каналы — на inbox_messages.
Последствия: единый InboxTab в LeadCard читает из обеих таблиц через
             unified view / merge на уровне API.
```

---

## Схема данных

### Новая таблица `inbox_messages` (migration 0025)

```sql
CREATE TABLE inbox_messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL,
  channel         VARCHAR(20) NOT NULL,   -- 'telegram' | 'max' | 'phone'
  direction       VARCHAR(10) NOT NULL,   -- 'inbound' | 'outbound'
  external_id     VARCHAR(255),
  sender_id       VARCHAR(255),           -- tg chat_id / max user_id / phone номер
  body            TEXT,
  media_url       TEXT,                   -- запись звонка
  call_duration   INTEGER,               -- секунды (только phone)
  call_status     VARCHAR(20),           -- 'answered' | 'missed' | 'busy'
  manager_user_id UUID REFERENCES users(id),
  delivered_at    TIMESTAMPTZ,
  read_at         TIMESTAMPTZ,
  transcript      TEXT,                   -- G4b: транскрипт звонка
  summary         TEXT,                   -- G4b: резюме MiMo
  stt_provider    VARCHAR(20),           -- G4b: 'salute'|'yandex'|'whisper'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_inbox_msg_external
  ON inbox_messages(channel, external_id)
  WHERE external_id IS NOT NULL;

CREATE INDEX ix_inbox_msg_lead    ON inbox_messages(lead_id, created_at DESC);
CREATE INDEX ix_inbox_msg_sender  ON inbox_messages(channel, sender_id);
CREATE INDEX ix_inbox_msg_unmatched ON inbox_messages(workspace_id)
  WHERE lead_id IS NULL;
```

> Примечание: колонки `transcript/summary/stt_provider` добавлены сразу в 0025,
> чтобы не плодить отдельную миграцию в G4b. Если транскрипция временно отключена —
> колонки просто остаются NULL.

### Новые колонки в `leads` (migration 0026)

> **Поправка:** изначальный спек утверждал, что `tg_chat_id` уже добавлен
> в Sprint 2.7 (migration 0022). На деле 0022 = `lead_agent_state`, и
> колонки `tg_chat_id` в схеме `leads` не существует. Добавляем обе
> колонки сразу в 0026.

```sql
ALTER TABLE leads ADD COLUMN tg_chat_id  VARCHAR(100);
ALTER TABLE leads ADD COLUMN max_user_id VARCHAR(100);

CREATE INDEX idx_leads_tg_chat_id  ON leads (workspace_id, tg_chat_id)
  WHERE tg_chat_id IS NOT NULL;
CREATE INDEX idx_leads_max_user_id ON leads (workspace_id, max_user_id)
  WHERE max_user_id IS NOT NULL;
```

---

## Структура расширения `app/inbox/`

Существующий пакет расширяется — не переписывается:

```
app/inbox/
  # --- СУЩЕСТВУЮЩЕЕ (Gmail, не трогаем) ---
  gmail_client.py      ✅
  oauth.py             ✅
  email_parser.py      ✅
  matcher.py           ✅
  processor.py         ✅
  sync.py              ✅
  services.py          ✅ (расширяется методами для новых каналов)
  routers.py           ✅ (добавляем новые endpoint'ы)
  models.py            ✅ (добавляем InboxMessage)
  schemas.py           ✅ (добавляем новые схемы)

  # --- НОВОЕ (Telegram / MAX / Phone) ---
  adapters/
    __init__.py
    base.py            — ChannelAdapter Protocol
    telegram.py        — TelegramAdapter
    max_messenger.py   — MaxAdapter
    phone.py           — PhoneAdapter (Mango)
  message_services.py  — MessageService (receive, send, match, list)
  message_tasks.py     — Celery: async_send, post_receive_hook, transcribe_call
  stt/
    __init__.py
    base.py            — SttProvider Protocol
    salute.py
    yandex.py
    whisper.py
    factory.py
```

### Протокол адаптера (`adapters/base.py`)

```python
from typing import Protocol
from app.inbox.schemas import WebhookPayload, OutboundMessage

class ChannelAdapter(Protocol):
    channel: str

    async def parse_webhook(self, raw: dict) -> WebhookPayload: ...
    async def send(self, msg: OutboundMessage) -> str: ...  # возвращает external_id
```

---

## G1 — Schema + skeleton (~0.5 дня) ✅

- [x] Migration 0025: `inbox_messages` (включая transcript/summary/stt_provider)
- [x] Migration 0026: `leads.tg_chat_id` + `leads.max_user_id` (обе колонки сразу)
- [x] `InboxMessage` SQLAlchemy модель в `app/inbox/models.py`
- [x] `app/inbox/adapters/base.py` — протокол
- [x] `app/inbox/message_services.py` — скелет (receive / match / list / assign;
  `send` поднимает `NotImplementedError` до G2/G3/G4)
- [x] `GET /leads/{lead_id}/inbox` — объединяет inbox_messages + (email
  через Activity, заполняется в G5)
- [x] `GET /api/inbox/unmatched/messages` — inbox_messages без lead_id
- [x] `PATCH /api/inbox/messages/{id}/assign` — назначить lead

Тесты: 4 mock (normalize_phone, match by tg_chat_id, receive dedup,
receive unmatched) — все зелёные.

> **Замечание:** на момент работы G1 на main валит 1 предсуществующий
> тест `test_inbox_matcher.py::test_processor_creates_activity_on_high_confidence_match`
> (processor.py и тест байт-в-байт совпадают с pre-Sprint-3.4 main —
> регрессия не связана с этим спринтом). Чинить отдельным фиксом.

---

## G2 — Telegram Business Bot (~2 дня) ✅

- [x] `app/inbox/adapters/telegram.py` — `TelegramAdapter` (parse_webhook
  для `message` и `business_message`, send через Bot API `sendMessage`)
- [x] `app/inbox/webhooks.py` — `POST /api/webhooks/telegram` с проверкой
  `X-Telegram-Bot-Api-Secret-Token` (constant-time compare)
- [x] `message_services.receive` теперь пишет Activity + Lead Agent
  refresh при matched inbound
- [x] `message_services.send` — outbound через адаптер, persists
  InboxMessage + Activity (direction='outbound')
- [x] `POST /leads/{lead_id}/inbox/send` (channel='telegram')
- [x] env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, опциональный
  `DEFAULT_WORKSPACE_ID` (для роутинга unmatched в multi-tenant сетапе)

Тесты — 11 mock (parse direct / business / no-text, adapter send happy /
no token / bad status, send service happy / no recipient / adapter
error, receive matched → Activity + agent refresh, receive unmatched).
Все зелёные.

### G2 — оригинальный спек (для справки)

### Предусловия

1. Telegram Premium аккаунт менеджера с включённым Telegram Business
2. Бот создан через @BotFather; подключён в настройках Telegram Business как «бот для бизнеса»
3. `TELEGRAM_BOT_TOKEN` и `TELEGRAM_WEBHOOK_SECRET` в `.env`

### Входящие

```
Клиент пишет менеджеру → Telegram Business → наш webhook

POST /api/webhooks/telegram
  Header: X-Telegram-Bot-Api-Secret-Token: {TELEGRAM_WEBHOOK_SECRET}
  Body: Telegram Update JSON
```

```python
# adapters/telegram.py
async def parse_webhook(self, raw: dict) -> WebhookPayload:
    msg = raw.get("message") or raw.get("business_message")
    return WebhookPayload(
        channel     = "telegram",
        direction   = "inbound",
        external_id = f"tg_{msg['message_id']}",
        sender_id   = str(msg["chat"]["id"]),
        body        = msg.get("text", ""),
    )
```

Сопоставление с лидом (в `message_services.match_logic`):

1. `leads.tg_chat_id == sender_id`
2. `leads.phone` нормализованный == номер (если клиент поделился)
3. Нет совпадения → `lead_id = NULL` → unmatched

После получения: запись в `inbox_messages` → Activity(`type='message', channel='telegram'`) → `lead_agent_refresh_suggestion(countdown=900)` если matched.

### Исходящие

```
POST /api/leads/{id}/inbox/send
  Body: { "channel": "telegram", "body": "текст" }

→ TelegramAdapter.send()
→ Telegram Bot API sendMessage / sendBusinessMessage
→ InboxMessage(direction='outbound') + Activity
```

### Регистрация webhook (один раз, команда)

```bash
curl "https://api.telegram.org/bot{TOKEN}/setWebhook" \
  -d url="https://crm.drinkx.tech/api/webhooks/telegram" \
  -d secret_token="{TELEGRAM_WEBHOOK_SECRET}"
```

Тесты: 4 mock (parse_webhook, match by tg_chat_id, match by phone, unmatched).

---

## G3 — MAX Bot (~1.5 дня)

### Предусловия

1. Бот создан через @MasterBot в MAX
2. `MAX_BOT_TOKEN` в `.env`

MAX Bot API по структуре близок к Telegram Bot API.

### Входящие

```
POST /api/webhooks/max

# adapters/max_messenger.py
async def parse_webhook(self, raw: dict) -> WebhookPayload:
    msg     = raw.get("message", {})
    user_id = str(msg.get("from", {}).get("userId", ""))
    return WebhookPayload(
        channel     = "max",
        direction   = "inbound",
        external_id = f"max_{msg.get('msgId')}",
        sender_id   = user_id,
        body        = msg.get("body", {}).get("text", ""),
    )
```

Сопоставление: `leads.max_user_id` → `leads.phone` → unmatched.

### Исходящие

```python
# MAX Bot API
POST https://botapi.max.ru/messages?access_token={MAX_BOT_TOKEN}
Body: {
  "recipient": { "userId": recipient_id },
  "body": { "text": body_text }
}
```

### Регистрация webhook (один раз)

```bash
curl "https://botapi.max.ru/subscriptions?access_token={MAX_BOT_TOKEN}" \
  -X POST \
  -d '{"url": "https://crm.drinkx.tech/api/webhooks/max"}'
```

Тесты: 3 mock (parse, match, send).

---

## G4 — IP-телефония Mango Office (~1 день) ✅

- [x] `app/inbox/adapters/phone.py` — `PhoneAdapter`: parse_webhook
  (call_end / missed_call, direction normalize, status='answered'/'missed',
  RU body lines), `initiate_call` (HMAC `sign = sha256(api_key + json + api_salt)`)
- [x] `compute_sign` helper (pinned by unit test) — единая точка правки
  под будущие версии Mango API
- [x] `POST /api/webhooks/phone` — form-encoded, validates `sign` over the
  `json` field if `MANGO_API_SALT` set, иначе принимает unsigned
  (dev-режим, лог-once warning)
- [x] `message_services.place_call` — НЕ пишет в `inbox_messages`
  (canonical row приходит через `call_end` webhook); возвращает Mango response
- [x] `POST /leads/{lead_id}/inbox/call` (`{from_extension}`) — 404/400/502/200
- [x] `receive` диспатчит `app.scheduled.jobs.transcribe_call` через 30 сек
  для `channel='phone'` + `call_status='answered'` + `media_url` (G4b наполнит)
- [x] env: `MANGO_API_KEY`, `MANGO_API_SALT`, `MANGO_API_BASE`

Тесты — 14 mock в `test_inbox_phone.py` (answered/missed/outbound parse,
duration-inferred status, compute_sign formula, initiate happy/no-config/bad-status,
place_call happy/no-phone/wraps-errors, transcribe dispatch yes/no on
answered+media / missed / answered-no-media). Все зелёные.

### G4 — оригинальный спек (для справки)

Телефония = **лог звонков** (автоматический) + **click-to-call** (кнопка в карточке).

### Входящие события (webhook Mango → CRM)

```
POST /api/webhooks/phone
Content-Type: application/x-www-form-urlencoded
```

```python
# adapters/phone.py
async def parse_webhook(self, raw: dict) -> WebhookPayload:
    duration  = int(raw.get("call_duration", 0))
    direction = "inbound" if raw.get("direction") == "from_client" else "outbound"
    caller    = raw.get("from_number") if direction == "inbound" else raw.get("to_number")
    body = f"Пропущенный звонок" if not duration else (
        f"{'Входящий' if direction == 'inbound' else 'Исходящий'} звонок, "
        f"{duration // 60}:{duration % 60:02d}"
    )
    return WebhookPayload(
        channel       = "phone",
        direction     = direction,
        external_id   = raw.get("call_id"),
        sender_id     = caller,
        body          = body,
        media_url     = raw.get("recording_url", ""),
        call_duration = duration,
        call_status   = "missed" if not duration else "answered",
    )
```

Сопоставление: `normalize_phone(leads.phone) == normalize_phone(caller)`

```python
# normalize_phone: убрать +7/8, пробелы, скобки, дефисы → 10 цифр
def normalize_phone(p: str) -> str:
    digits = re.sub(r"\D", "", p or "")
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = digits[1:]
    return digits  # ожидаем 10 цифр
```

### Click-to-call

```
POST /api/leads/{id}/inbox/call
Body: { "from_extension": "101" }  # внутренний номер менеджера

→ POST https://app.mango-office.ru/vpbx/commands/callback
  {
    "vpbx_api_key": "...",
    "sign": HMAC_SHA256(key + body),
    "from": { "extension": "101" },
    "to":   { "number": lead.phone }
  }
→ 200 { "status": "dialing" }
```

Mango пришлёт `call_end` webhook после завершения — запись попадёт в ленту автоматически.

### Настройка в Mango (один раз)

```
Личный кабинет → Интеграции → Webhooks
URL: https://crm.drinkx.tech/api/webhooks/phone
События: call_end, missed_call
```

Тесты: 4 mock (call_end, missed_call, normalize_phone, click-to-call payload).

---

## G4b — Транскрипция и резюме звонка (~1.5 дня) ✅

- [x] `app/inbox/stt/base.py` — `SttProvider` Protocol + `SttError`
- [x] `app/inbox/stt/salute.py` — `SaluteSpeechProvider`: OAuth2
  токен с in-memory кешем на 1700 сек (28 мин), STT через
  `smartspeech.sber.ru/rest/v1/speech:recognize` (audio/mpeg), толерантный
  парсинг ответа (молчание → "" вместо exception)
- [x] `app/inbox/stt/whisper.py` — placeholder
- [x] `app/inbox/stt/factory.py` — `get_stt_provider()` по env
- [x] `app/inbox/message_tasks.transcribe_call_async` — orchestrator:
  download audio → STT → MiMo summary (`TaskType.prefilter`,
  `max_tokens=200`) → UPDATE `inbox_messages.transcript/summary/stt_provider`
  → обновляет Activity.body на «📞 Звонок M:SS · {summary}»
  → ставит `lead_agent_refresh_suggestion(countdown=60)` для matched
- [x] Resilient: любая ошибка отдельного шага (audio download, STT,
  summary) НЕ роняет — записывает что есть и возвращает status-код
- [x] env: `STT_PROVIDER` (default `salute`), `SALUTE_CLIENT_ID`,
  `SALUTE_CLIENT_SECRET`, `SALUTE_SCOPE` (default `SALUTE_SPEECH_PERS`)

Тесты — 9 mock в `test_inbox_transcribe.py` (factory default + fallback,
salute token caching + oauth failure + silent audio + missing creds,
orchestrator happy path + missed-call skip + STT failure persists provider).

### G4b — оригинальный спек (для справки)

Автоматически запускается после получения `call_end` с непустым `recording_url`.

### Важное разграничение

Два разных сервиса Сбера, которые работают вместе:

| Сервис | Роль | Аналог в нашем стеке |
|---|---|---|
| **SaluteSpeech** | STT: аудио → текст | — (новый провайдер) |
| **GigaChat** | LLM: текст → резюме | MiMo (уже есть) |

Для резюме используем **MiMo Flash** — он уже в стеке. SaluteSpeech только для транскрипции.

---

### ADR-024 — SttProvider абстракция (по образцу ADR-018 для LLM)

```
Проблема:  разные STT-провайдеры (SaluteSpeech, Yandex SpeechKit, Whisper)
           дают разное качество на русском; хочется переключаться без кода.
Решение:   SttProvider Protocol + фабрика get_stt_provider().
           Активный провайдер читается из STT_PROVIDER env.
           Порядок предпочтений: salute > yandex > whisper.
Последствия: смена провайдера = одна переменная окружения.
```

### Структура `app/inbox/stt/`

```
app/inbox/stt/
  __init__.py
  base.py        — SttProvider Protocol
  salute.py      — SaluteSpeechProvider   ← рекомендуемый по умолчанию
  yandex.py      — YandexSpeechKitProvider ← альтернатива
  whisper.py     — WhisperProvider         ← fallback / тест
  factory.py     — get_stt_provider()
```

### Протокол (`base.py`)

```python
from typing import Protocol

class SttProvider(Protocol):
    provider_name: str

    async def transcribe(self, audio_bytes: bytes, language: str = "ru") -> str:
        """Возвращает текст транскрипта."""
        ...
```

### SaluteSpeech (`salute.py`)

```python
# Sber SaluteSpeech API
# Docs: https://developers.sber.ru/docs/ru/salutespeech/recognition/rest/recognition-guide
class SaluteSpeechProvider:
    provider_name = "salute"

    def __init__(self):
        self.client_id     = settings.SALUTE_CLIENT_ID
        self.client_secret = settings.SALUTE_CLIENT_SECRET
        self._token: str | None = None
        self._token_expires: float = 0

    async def _get_token(self) -> str:
        """OAuth2 токен, кешируется на 30 минут."""
        if self._token and time.time() < self._token_expires:
            return self._token
        resp = await httpx.post(
            "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            headers={"Authorization": f"Basic {self._b64_creds()}"},
            data={"scope": "SALUTE_SPEECH_PERS"},
        )
        self._token = resp.json()["access_token"]
        self._token_expires = time.time() + 1700  # ~28 мин
        return self._token

    async def transcribe(self, audio_bytes: bytes, language: str = "ru") -> str:
        token = await self._get_token()
        resp = await httpx.post(
            "https://smartspeech.sber.ru/rest/v1/speech:recognize",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "audio/mpeg",  # mp3 от Mango
            },
            content=audio_bytes,
            params={"language": language},
            timeout=60,
        )
        return resp.json().get("result", [{}])[0].get("normalized_text", "")
```

### Yandex SpeechKit (`yandex.py`)

```python
# Yandex SpeechKit API — альтернатива, аналогичное качество для RU
# Docs: https://yandex.cloud/ru/docs/speechkit/stt/
class YandexSpeechKitProvider:
    provider_name = "yandex"

    async def transcribe(self, audio_bytes: bytes, language: str = "ru") -> str:
        resp = await httpx.post(
            "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
            headers={"Authorization": f"Api-Key {settings.YANDEX_STT_API_KEY}"},
            content=audio_bytes,
            params={"lang": language, "format": "mp3"},
            timeout=60,
        )
        return resp.json().get("result", "")
```

### Фабрика (`factory.py`)

```python
def get_stt_provider() -> SttProvider:
    provider = os.getenv("STT_PROVIDER", "salute")
    match provider:
        case "salute":  return SaluteSpeechProvider()
        case "yandex":  return YandexSpeechKitProvider()
        case "whisper": return WhisperProvider()
        case _:         return SaluteSpeechProvider()
```

### Схема данных

Колонки `transcript`, `summary`, `stt_provider` уже добавлены в migration 0025
(вместе с `inbox_messages`). Дополнительной миграции не требуется.

`stt_provider` — для отладки: видно, каким провайдером сделана транскрипция.

### Celery task `transcribe_call`

```python
@celery_app.task(bind=True, max_retries=2)
def transcribe_call(self, message_id: str) -> None:
    msg = get_inbox_message(message_id)
    if not msg or not msg.media_url or msg.call_status == "missed":
        return

    # Шаг 1: скачать аудио с Mango
    audio_bytes = httpx.get(msg.media_url, timeout=30).content

    # Шаг 2: STT через выбранный провайдер
    stt = get_stt_provider()
    try:
        transcript = asyncio.run(stt.transcribe(audio_bytes))
    except Exception as exc:
        logger.warning("STT failed (%s): %s", stt.provider_name, exc)
        return  # не падаем — запись всё равно доступна по ссылке

    # Шаг 3: MiMo Flash → резюме (уже в стеке)
    summary = complete_with_fallback(
        task_type=TaskType.prefilter,
        prompt=(
            "Ниже транскрипт телефонного разговора менеджера с клиентом DrinkX. "
            "Напиши резюме в 2-3 предложениях: цель звонка, что спросил клиент, "
            "о чём договорились, следующий шаг.\n\n"
            f"Транскрипт:\n{transcript[:3000]}"
        ),
        max_tokens=200,
    )

    # Шаг 4: сохранить
    update_inbox_message(
        message_id,
        transcript=transcript,
        summary=summary,
        stt_provider=stt.provider_name,
    )

    # Обновить Activity.body — в ленте лида будет резюме, а не «Звонок 4:12»
    dur = msg.call_duration or 0
    update_activity_body(
        ref_id=message_id,
        body=f"📞 Звонок {dur // 60}:{dur % 60:02d} · {summary}",
    )

    # Триггер Lead Agent с новым контекстом
    if msg.lead_id:
        lead_agent_refresh_suggestion.apply_async(
            args=[str(msg.lead_id)], countdown=60
        )
```

### Диспетчеризация

В `message_services.receive()` после сохранения `call_end`:

```python
if payload.channel == "phone" and payload.media_url and payload.call_status == "answered":
    transcribe_call.apply_async(args=[str(message.id)], countdown=30)
    # countdown=30 — даём Mango время финализировать файл записи
```

### Стоимость (оценка)

| Провайдер | Цена/мин | Звонок 5 мин | 50 звонков/день |
|---|---|---|---|
| SaluteSpeech | ~₽1.5–2 | ~₽8–10 | ~₽400–500/день |
| Yandex SpeechKit | ~$0.02 | ~$0.10 | ~$5/день |
| + MiMo Flash резюме | ~$0.001 | — | ~$0.05/день |

Yandex SpeechKit дешевле и с долларовым биллингом. SaluteSpeech — рублёвый,
лучше для компаний с требованием хранить данные в РФ.

### Как выглядит в карточке лида

```
📞 Входящий звонок, 4:12   Сегодня 11:42
────────────────────────────────────────────────────────
Клиент уточнял условия пилота. Спросил про рассрочку
на 6 месяцев. Менеджер пообещал выслать КП до пятницы.

[▶ Запись]  [📄 Показать транскрипт ▾]

▾ Транскрипт (SaluteSpeech)
  Менеджер: Добрый день, Андрей...
  Клиент: Да, добрый. Хотел уточнить...
  ...
```

### ENV-переменные (новые)

```env
STT_PROVIDER=salute          # salute | yandex | whisper

# SaluteSpeech (если STT_PROVIDER=salute)
SALUTE_CLIENT_ID=
SALUTE_CLIENT_SECRET=

# Yandex SpeechKit (если STT_PROVIDER=yandex)
YANDEX_STT_API_KEY=
```

Тесты: 4 mock (salute transcribe, yandex transcribe, missed call skip, summary generation).

---

## G5 — Gmail Send (исходящие письма) (~1 день)

Gmail-интеграция уже читает почту. Добавляем **отправку** из карточки лида.

```
POST /api/leads/{id}/inbox/send
Body: { "channel": "email", "body": "текст", "subject": "Тема" }

→ gmail_client.send_message(to=lead.email, subject=..., body=...)
→ Activity(type='email', direction='outbound')
→ InboxItem или прямой Activity без inbox_items (обсудить)
```

Требует: пользователь подключил Gmail с `gmail.send` scope.

Если scope ещё не запрошен — при `Подключить Gmail` запросить оба scope сразу:
`gmail.readonly` + `gmail.send`.

Существующие подключения без `send` scope → inline-уведомление «Переподключите Gmail для отправки».

Тесты: 2 mock (send success, missing scope → 403).

---

## G6 — Frontend: InboxTab в LeadCard (~2 дня) ✅

- [x] TypeScript-типы `InboxFeedEntry/Out`, `InboxFeedChannelLink`,
  `InboxSendIn`, `InboxMessageOut`, `InboxCallIn/Out` в `apps/web/lib/types.ts`
- [x] `apps/web/lib/hooks/use-lead-inbox.ts` — `useLeadInbox` (polling 10s),
  `useLeadInboxSend`, `useLeadInboxCall`
- [x] `apps/web/components/lead-card/InboxTab.tsx` — фильтр-бар
  [Все/Gmail/Telegram/Телефон], лента с channel badge + direction label,
  collapsible транскрипт под звонками, composer (Telegram), кнопка
  «Позвонить» с localStorage-кешем extension
- [x] 4-й таб «Переписка» в `LeadCard.tsx` (мобильный select + desktop tabs)
- [x] `npm run typecheck` clean, lint clean для InboxTab

> Email-плечо в `/leads/{id}/inbox` пока пустое — Gmail-переписка
> отображается в табе «Активность»; полная отправка из карточки —
> G5 (вне MVP-варианта B).
>
> Композер пока только Telegram. MAX (G3) и Email-send (G5) — в спек,
> не в MVP. UI чипа сделан так, чтобы добавление каналов было одним
> элементом в массиве.

### G6 — оригинальный спек (для справки)

Новый 6-й таб «Переписка» в карточке лида (существующие 5: Info / Activities / Contacts / AI Brief / Score).

### Wireframe

```
┌─────────────────────────────────────────────────────────┐
│  [Все▼]  [Gmail]  [Telegram]  [MAX]  [Телефон]          │
│                                      [+ Написать ▾]     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ✉  Пт 14:32                            ВХОДЯЩИЙ       │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Re: Демо по DrinkX                                │  │
│  │ Спасибо, буду на демо в пятницу в 11:00           │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  📱 Сб 10:15                            ВХОДЯЩИЙ       │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Telegram                                          │  │
│  │ Добрый день! Подскажите — есть рассрочка?         │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  📞 Сб 11:42                        ВХОДЯЩИЙ ЗВОНОК    │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Входящий звонок, 4:12   [▶ Запись]                │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Ответить в: [Telegram ▾]                               │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Написать сообщение...                             │  │
│  └───────────────────────────────────────────────────┘  │
│                                          [Отправить]    │
└─────────────────────────────────────────────────────────┘
```

### API

`GET /api/leads/{id}/inbox` — объединяет inbox_items (email) + inbox_messages (tg/max/phone):

```json
{
  "messages": [
    { "channel": "email",    "direction": "inbound",  "body": "...", "subject": "...", "created_at": "..." },
    { "channel": "telegram", "direction": "inbound",  "body": "...", "created_at": "..." },
    { "channel": "phone",    "direction": "inbound",  "call_duration": 252, "media_url": "...", "created_at": "..." }
  ],
  "channels_linked": {
    "email":    { "linked": true,  "address": "client@example.com" },
    "telegram": { "linked": true,  "chat_id": "123456" },
    "max":      { "linked": false, "user_id": null },
    "phone":    { "linked": true,  "number": "+79161234567" }
  }
}
```

### Компоненты

```
apps/web/components/lead/InboxTab.tsx        — основной таб
apps/web/components/lead/InboxMessage.tsx    — одно сообщение (channel badge)
apps/web/components/lead/InboxComposer.tsx   — поле ввода + выбор канала
apps/web/hooks/useLeadInbox.ts               — TanStack Query: fetch + send + 10s poll
```

Если канал не привязан → composer показывает: «Укажите Telegram chat ID в профиле лида».

### Click-to-call

Кнопка 📞 рядом с номером телефона в Info-табе → `POST /api/leads/{id}/inbox/call`.

---

## G7 — Unmatched messages (~0.5 дня) ✅

- [x] `useInboxUnmatchedMessages` (polling 15с) + `useAssignInboxMessage`
  в `apps/web/lib/hooks/use-inbox.ts`
- [x] `apps/web/components/inbox/UnmatchedMessagesSection.tsx` — секция
  «Мессенджеры и звонки» под существующим email-списком, с inline
  LeadSearchPicker и кнопкой «Привязать к лиду» → PATCH
  `/api/inbox/messages/{id}/assign`
- [x] Секция автоматически скрыта, если нематченных нет
- [x] После назначения: оптимистичное скрытие строки + invalidate
  unmatched + invalidate lead-inbox целевого лида

### G7 — оригинальный спек (для справки)

Входящие без `lead_id` — `/inbox` страница уже существует (для Gmail).
Добавляем секцию «Мессенджеры» рядом с существующей секцией email.

```
PATCH /api/inbox/messages/{id}/assign
Body: { "lead_id": "..." }
```

После назначения: сообщение исчезает из unmatched, появляется в InboxTab лида.

---

## G8 — Sprint close (~0.5 дня)

- `docs/SPRINT_3_4_INBOX_CHANNELS_REPORT.md`
- Brain rotation (00 + 02 + 04)
- Smoke: все 4 webhook endpoint'а, отправка из CRM, запись звонка в ленте

---

## ENV-переменные (новые)

```env
# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=

# MAX
MAX_BOT_TOKEN=
MAX_WEBHOOK_SECRET=

# Mango
MANGO_API_KEY=
MANGO_API_SALT=

# STT (G4b)
STT_PROVIDER=salute          # salute | yandex | whisper
SALUTE_CLIENT_ID=
SALUTE_CLIENT_SECRET=
YANDEX_STT_API_KEY=
```

Добавить в `/opt/drinkx-crm/infra/production/.env` вручную.

---

## Риски

| Риск | Уровень | Митигация |
|---|---|---|
| MAX Bot API молодой, документация меняется | Средний | Тонкий адаптер, парсим raw dict без жёстких ключей |
| Mango шлёт дубли webhook при сетевом сбое | Низкий | UNIQUE INDEX (channel, external_id) — dedup на БД |
| Записи звонков Mango хранятся ограниченно | Средний | Сохраняем `recording_url`; предупредить менеджеров |
| `leads.phone` в разных форматах | Средний | `normalize_phone()` — убираем +7/8, пробелы, скобки |
| Gmail `send` scope у существующих юзеров отсутствует | Низкий | Inline-предложение переподключить Gmail |
| Whisper не справляется с фоновым шумом / тихим голосом | Низкий | Сохраняем transcript как есть; резюме MiMo сглаживает артефакты |
| Запись Mango недоступна сразу после `call_end` | Низкий | `countdown=30` в Celery task перед скачиванием |

---

## Acceptance criteria

- [ ] `GET /api/leads/{id}/inbox` возвращает email + tg + max + phone в хронологии
- [ ] Входящий Telegram → `inbox_messages` + Activity в ленте
- [ ] Входящий MAX → то же
- [ ] Mango `call_end` → `inbox_messages` с duration + recording_url
- [ ] Пропущенный звонок → `call_status = 'missed'`, транскрипция не запускается
- [ ] Состоявшийся звонок → Celery task запускает транскрипцию через 30 сек
- [ ] После транскрипции: `inbox_messages.transcript` и `.summary` заполнены
- [ ] Activity в ленте лида показывает резюме звонка (не просто «Звонок 4:12»)
- [ ] Кнопка «Показать транскрипт» разворачивает полный текст
- [ ] Lead Agent получает контекст звонка через 60 сек после транскрипции
- [ ] `POST /api/leads/{id}/inbox/send` (telegram) — доставляет сообщение
- [ ] `POST /api/leads/{id}/inbox/send` (max) — доставляет сообщение
- [ ] `POST /api/leads/{id}/inbox/send` (email) — отправляет через Gmail
- [ ] `POST /api/leads/{id}/inbox/call` — инициирует звонок через Mango
- [ ] Дублирующий webhook не создаёт дубль записи
- [ ] Нематченное сообщение → `/inbox` unmatched секция
- [ ] InboxTab рендерит все 4 канала с фильтром по каналу
- [ ] `pnpm typecheck` clean, все существующие тесты зелёные

---

## Оценка

| Gate | Дней |
|---|---|
| G1 Schema + skeleton | 0.5 |
| G2 Telegram | 2.0 |
| G3 MAX | 1.5 |
| G4 Mango | 1.0 |
| G5 Gmail Send | 1.0 |
| G6 InboxTab frontend | 2.0 |
| G4b Транскрипция + резюме | 1.5 |
| G7 Unmatched | 0.5 |
| G8 Close | 0.5 |
| **Итого** | **~10.5 дней** |

**MVP-версия (5 дней):** только Telegram + звонки (без MAX и Gmail Send).
G2 + G4 + G6 (только Telegram/Phone в composer) + G1/G7/G8.

**MVP-версия (~6 дней):** Telegram + звонки + транскрипция (без MAX и Gmail Send).
Gates: G1 + G2 + G4 + G4b + G6 (только Telegram/Phone в UI) + G7 + G8.
