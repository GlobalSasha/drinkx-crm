// @vitest-environment node
import { describe, expect, it } from "vitest";
import { GET } from "./route";

describe("GET /kp", () => {
  it("отдаёт конфигуратор как HTML и запрещает кэшировать", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/html; charset=utf-8");
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    expect(await res.text()).toContain("<title>DrinkX КП</title>");
  });

  // Сборщик конфигуратора однажды обрезал скрипт на середине: страница
  // открывалась, но расчёт был пуст. Ловим такой файл при замене kp.html.
  it("файл цел: скрипты закрыты и разбираются", async () => {
    const html = await (await GET()).text();
    const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)];
    expect(scripts.length).toBe(html.split("<script").length - 1);
    expect(scripts.length).toBeGreaterThan(0);
    for (const [, code] of scripts) {
      expect(() => new Function(code)).not.toThrow();
    }
    expect(html.trimEnd().endsWith("</html>")).toBe(true);
  });
});
