# Подключение лендингов к CRM

Документация для маркетолога / дизайнера, поднимающего лендинг в Claude
или v0. Минимум — 5 минут до рабочей формы и первой заявки в CRM.

## Что вы получите

- Одна форма на лендинге → одна заявка в CRM в **Базе лидов** через
  ~5 секунд.
- На карточке лида видно «🌐 Лендинг: <имя формы>» — клик ведёт в пул,
  отфильтрованный по этому лендингу.
- Все UTM-параметры с URL фиксируются и показываются структурно во
  вкладке «Сделка и AI» → «Источник».
- На странице «Формы» (admin/head) — сводка: заявки за 7д / 30д /
  взято в работу / конверсия дальше первого этапа.

## Шаг 1. Создать форму в CRM

1. Открыть `https://crm.drinkx.tech/forms` (нужны права admin или head).
2. Кнопка «Новая форма».
3. Заполнить:
   - **Имя** — как форма будет называться на карточке лида: «HoReCa
     МСК», «АЗС лендинг», «Калькулятор ROI».
   - **Slug** — короткий URL-safe идентификатор латиницей:
     `horeca-msk`, `azs-landing`, `roi-calc`. Slug **уникален
     глобально**, его потом не поменять.
   - **Поля** — минимум `phone` + `email`. Опционально `name`,
     `company_name`, `notes`. Имена полей не важны — backend знает
     RU/EN-синонимы (`phone`/`телефон`/`тел`; `email`/`почта`;
     `name`/`имя`; и т.д.), любое непонятное поле сохраняется в
     `raw_payload`.
   - **Целевая воронка / стадия** — куда падает лид. По умолчанию —
     первый этап «Новые клиенты».
4. Сохранить → скопировать slug.

## Шаг 2. Подключить форму на лендинг

Два паттерна. Выбирайте по технологии лендинга.

### Паттерн A1 — статический HTML с embed.js

Подходит для лендингов, сгенерированных Claude в виде одного
`index.html`, или для любых не-React сайтов где можно вставить
`<script>` в `<head>` / `<body>`.

```html
<!-- В <body> там, где должна появиться форма: -->
<div id="drinkx-form"></div>

<!-- В <head> или прямо после <div>: -->
<script
  async
  src="https://crm.drinkx.tech/api/public/forms/horeca-msk/embed.js"
></script>
```

Замените `horeca-msk` на ваш slug. Скрипт самодостаточный (без
зависимостей), рендерит форму внутрь `<div id="drinkx-form">`.
Стилизация — наша дефолтная; если нужен полный контроль над дизайном,
используйте паттерн A2.

### Паттерн A2 — React / Next.js (v0 / Claude-generated)

Подходит для лендингов на React/Next.js. Скопируйте компонент ниже к
себе на лендинг. Стилизуйте Tailwind-классами как угодно — UI ваш,
контракт с CRM один: один POST на `/api/public/forms/{slug}/submit`.

```tsx
"use client";

import { useEffect, useState, type FormEvent } from "react";

const SLUG = "horeca-msk"; // ← подставьте свой slug
const ENDPOINT = `https://crm.drinkx.tech/api/public/forms/${SLUG}/submit`;
const UTM_KEYS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_content",
  "utm_term",
];

export function LeadForm() {
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [utm, setUtm] = useState<Record<string, string>>({});
  const [state, setState] = useState<"idle" | "sending" | "ok" | "error">("idle");

  // Read UTM params from the landing URL once on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const collected: Record<string, string> = {};
    for (const key of UTM_KEYS) {
      const value = params.get(key);
      if (value) collected[key] = value;
    }
    setUtm(collected);
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setState("sending");
    try {
      const res = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, email, name, utm }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setState("ok");
    } catch {
      setState("error");
    }
  }

  if (state === "ok") {
    return (
      <div className="p-6 bg-emerald-50 text-emerald-900 rounded-2xl">
        Спасибо! Мы свяжемся с вами в ближайшее время.
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3 max-w-md">
      <input
        type="tel"
        required
        placeholder="Телефон"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        className="px-4 py-2 rounded-xl border border-neutral-300"
      />
      <input
        type="email"
        required
        placeholder="Email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="px-4 py-2 rounded-xl border border-neutral-300"
      />
      <input
        type="text"
        placeholder="Имя (необязательно)"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="px-4 py-2 rounded-xl border border-neutral-300"
      />
      <button
        type="submit"
        disabled={state === "sending"}
        className="px-4 py-2 rounded-xl bg-[#FF4E00] text-white font-semibold disabled:opacity-50"
      >
        {state === "sending" ? "Отправляем…" : "Получить предложение"}
      </button>
      {state === "error" && (
        <p className="text-rose-600 text-sm">
          Не удалось отправить. Попробуйте ещё раз через минуту.
        </p>
      )}
    </form>
  );
}
```

## UTM-параметры

CRM читает пять ключей из `payload.utm`:

| Ключ | Что обычно содержит |
|---|---|
| `utm_source` | источник трафика — `vk` / `yandex` / `instagram` / `linkedin` / `email` |
| `utm_medium` | тип канала — `cpc` / `social` / `email` / `referral` |
| `utm_campaign` | имя кампании — `horeca-q3` / `azs-launch` |
| `utm_content` | конкретный креатив / объявление — `reels-1` / `banner-blue` |
| `utm_term` | поисковый запрос или ключевое слово |

Передавайте их в JSON-теле как объект `utm`:

```json
{
  "phone": "+79991234567",
  "email": "client@example.com",
  "utm": {
    "utm_source": "vk",
    "utm_campaign": "horeca-q3",
    "utm_content": "reels-1"
  }
}
```

`embed.js` (паттерн A1) автоматически читает UTM из URL и кладёт в
submit. Компонент из паттерна A2 делает то же самое в `useEffect`.

## Шаг 3. Тестовый прогон

1. Откройте лендинг в браузере, заполните и отправьте форму.
2. В CRM откройте `/leads-pool`, отфильтруйте по своей форме («Источник»
   → имя вашей формы). Лид появится за ~5 секунд.
3. Откройте лид → в шапке должен быть чип «🌐 Лендинг: <имя>».
4. На вкладке «Сделка и AI» — карточка «Источник» с form_name +
   source_domain + UTM-таблицей.
5. На `/forms` рядом с вашей формой — счётчик «1 за 7 дней».

Прогоните ещё раз с UTM в URL, например:
`?utm_source=test&utm_campaign=smoke&utm_medium=manual`.
Переоткройте новый лид → UTM-таблица должна отразить эти значения.

## CORS и rate-limits

- Endpoint `https://crm.drinkx.tech/api/public/forms/*` — wildcard-CORS
  (по дизайну, любые origins). Allowlist не нужен.
- Rate-limit: per `(slug, IP)`, защищает от ботов. Нормальные
  пользователи не упрутся.

## Что НЕ нужно делать

- Не нужно подключать никаких SDK / npm-пакетов. Один endpoint, чистый POST.
- Не нужно ставить captcha — rate-limit + AI-фильтрация в Inbox
  закрывают спам.
- Не нужно хранить slug в `.env` — он публичный по своей природе
  (видно в исходниках лендинга всё равно).

## Когда нужна помощь

- Лид не приходит → проверьте Network tab в браузере. POST должен
  вернуть `200`. Если `404` — slug опечатан или форма выключена.
- Лид приходит без UTM → проверьте что URL лендинга открыт с
  UTM-параметрами. UTM читаются с `window.location.search` на момент
  монтирования формы.
- Лид приходит, но имя формы пустое (`📥 Заявка с формы`) → форму
  удалили в админке, а старый embed на лендинге продолжает работать.
  Создайте форму заново или замените slug.
