import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { createBrowserClient } = vi.hoisted(() => ({ createBrowserClient: vi.fn() }));
vi.mock("@supabase/ssr", () => ({ createBrowserClient }));

import { getSupabaseBrowserClient } from "./browser";

function env(flag: string, url = "", key = "") {
  vi.stubEnv("NEXT_PUBLIC_DEV_AUTH_BYPASS", flag);
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", url);
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", key);
}

beforeEach(() => {
  createBrowserClient.mockReset();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getSupabaseBrowserClient", () => {
  it("в локальном режиме без настроек подставляет заглушки вместо пустых значений", () => {
    env("1");

    getSupabaseBrowserClient();

    const [url, key] = createBrowserClient.mock.calls[0];
    expect(url).toBeTruthy();
    expect(key).toBeTruthy();
  });

  it("в локальном режиме оставляет настоящие настройки, если они заданы", () => {
    env("1", "https://real.example", "real-key");

    getSupabaseBrowserClient();

    expect(createBrowserClient).toHaveBeenCalledWith("https://real.example", "real-key");
  });

  it("без флага заглушек нет", () => {
    env("");

    getSupabaseBrowserClient();

    expect(createBrowserClient).toHaveBeenCalledWith("", "");
  });

  it("в production-сборке флаг не включает заглушки", () => {
    env("1");
    vi.stubEnv("NODE_ENV", "production");

    getSupabaseBrowserClient();

    expect(createBrowserClient).toHaveBeenCalledWith("", "");
  });
});
