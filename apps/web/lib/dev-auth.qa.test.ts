/**
 * QA-дополнения к DEV-FIX-03 (см. lib/dev-auth.test.ts — сценарии a/b/c
 * на чистой функции `isDevAuthBypass`).
 *
 * Здесь — интеграционная проверка `middleware.ts`: без флага (или в
 * production) запрос обязан по-прежнему идти через `updateSession`
 * (реальный `supabase.auth.getUser()`), а не молча получать stub-личность.
 * `isDevAuthBypass` сама по себе не гарантирует, что `middleware.ts`
 * действительно её проверяет перед тем, как звать `updateSession` — это и
 * ловит эта пара тестов.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

const { updateSession } = vi.hoisted(() => ({
  updateSession: vi.fn(),
}));
vi.mock("@/lib/supabase/middleware", () => ({ updateSession }));

function makeRequest(pathname: string): NextRequest {
  return new NextRequest(new URL(pathname, "http://localhost:3000"), { headers: new Headers() });
}

beforeEach(() => {
  vi.resetModules();
  updateSession.mockReset();
  updateSession.mockResolvedValue({
    response: { cookies: { set: vi.fn() } },
    user: null,
  });
});

describe("middleware fail-closed без флага обхода", () => {
  it("без NEXT_PUBLIC_DEV_AUTH_BYPASS зовёт updateSession (getUser)", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH_BYPASS", "");
    vi.stubEnv("NODE_ENV", "development");
    const { middleware } = await import("./../middleware");
    await middleware(makeRequest("/today"));
    expect(updateSession).toHaveBeenCalledTimes(1);
    vi.unstubAllEnvs();
  });

  it("флаг включён, но NODE_ENV=production — тоже зовёт updateSession", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH_BYPASS", "1");
    vi.stubEnv("NODE_ENV", "production");
    const { middleware } = await import("./../middleware");
    await middleware(makeRequest("/today"));
    expect(updateSession).toHaveBeenCalledTimes(1);
    vi.unstubAllEnvs();
  });

  it("флаг + development — обход есть, updateSession не зовётся", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH_BYPASS", "1");
    vi.stubEnv("NODE_ENV", "development");
    const { middleware } = await import("./../middleware");
    // NextResponse.next() внутри тестовой (не Next-рантайм) среды капризничает
    // на заголовках — нас здесь интересует только факт вызова updateSession,
    // а не итоговый Response, поэтому ошибка после ветвления игнорируется.
    await middleware(makeRequest("/today")).catch(() => undefined);
    expect(updateSession).not.toHaveBeenCalled();
    vi.unstubAllEnvs();
  });
});
