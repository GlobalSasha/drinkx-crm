import { readFile } from "node:fs/promises";

// Карта дистрибьюторов и конкурентов — самодостаточный HTML. В репозитории
// его нет: репозиторий публичный, а карта — внутренний материал. На сервере
// файл лежит в /var/www/drinkx-map/ (nginx отдаёт его по /karta/ под своим
// паролем), а в контейнер web эта папка смонтирована только для чтения —
// см. infra/production/docker-compose.yml. Обновили файл на сервере —
// в CRM сразу новая версия, без выкладки.
//
// Route handler, а не public/: middleware пускает без входа любой путь с
// расширением, а у /map-embed его нет — сюда доходит только вошедший.
// Страница с сайдбаром — app/(app)/map, она показывает этот адрес во фрейме.
const MAP_HTML = process.env.MAP_HTML_PATH ?? "/srv/drinkx-map/karta-rf.html";

// Ссылки в файле относительные (index.html, karta.html, otchety/...): они
// ведут на соседние страницы статического сайта /karta/, а не в CRM.
const BASE_TAG = '<base href="/karta/">';

const NOT_FOUND_HTML =
  '<!doctype html><meta charset="utf-8"><body style="font-family:system-ui;padding:24px">' +
  "Файл карты не найден на сервере.</body>";

export const dynamic = "force-dynamic";

export async function GET() {
  let html: string;
  try {
    html = await readFile(MAP_HTML, "utf8");
  } catch {
    return new Response(NOT_FOUND_HTML, {
      status: 404,
      headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
    });
  }
  return new Response(html.replace("<head>", `<head>${BASE_TAG}`), {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
