// @vitest-environment node
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterAll, describe, expect, it, vi } from "vitest";

// Настоящей карты в репозитории нет (внутренний материал) — подменяем файл.
const dir = mkdtempSync(path.join(tmpdir(), "map-embed-"));
const file = path.join(dir, "karta-rf.html");

async function loadGET(mapPath: string) {
  vi.resetModules();
  vi.stubEnv("MAP_HTML_PATH", mapPath);
  return (await import("./route")).GET;
}

afterAll(() => {
  vi.unstubAllEnvs();
  rmSync(dir, { recursive: true, force: true });
});

describe("GET /map-embed", () => {
  it("отдаёт карту как HTML, без кэша, со ссылками на сайт /karta/", async () => {
    writeFileSync(file, "<html><head><title>Карта</title></head><body></body></html>");
    const res = await (await loadGET(file))();
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/html; charset=utf-8");
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    expect(await res.text()).toContain('<head><base href="/karta/"><title>Карта</title>');
  });

  it("нет файла на сервере — 404 с понятным текстом, а не падение", async () => {
    const res = await (await loadGET(path.join(dir, "missing.html")))();
    expect(res.status).toBe(404);
    expect(await res.text()).toContain("Файл карты не найден");
  });
});
