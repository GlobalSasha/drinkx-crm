import { readFile } from "node:fs/promises";
import path from "node:path";

// Конфигуратор КП — готовый самодостаточный HTML из репозитория
// drinkx-sales-configurator (dist/kp.html), лежит рядом как есть.
//
// Почему route handler, а не public/kp.html: middleware пропускает без входа
// любой путь с расширением, а в файле видны себестоимость и прибыль. У /kp
// расширения нет, поэтому сюда доходит только вошедший. Маршрут вне (app) —
// страница открывается без сайдбара, как app/quote/[quoteId]/print.
//
// Путь собран из литералов от process.cwd(): так сборка standalone видит
// файл и кладёт его в образ.
const KP_HTML = path.join(process.cwd(), "app/kp/kp.html");

export const dynamic = "force-dynamic";

export async function GET() {
  const html = await readFile(KP_HTML, "utf8");
  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
