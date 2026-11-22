import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.hoisted(() => ({
  support: "supported" as string,
  subscription: null as unknown,
}));
const apiGet = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api-client", () => ({ api: { get: apiGet, post: vi.fn() } }));
vi.mock("@/lib/push", () => ({
  readPushEnv: () => ({}),
  detectPushSupport: () => pushMock.support,
  currentSubscription: () => Promise.resolve(pushMock.subscription),
  enablePush: vi.fn(),
  disablePush: vi.fn(),
}));

import { PushSettings } from "./PushSettings";

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <PushSettings>
        <p>старая кнопка для компьютера</p>
      </PushSettings>
    </QueryClientProvider>,
  );
}

describe("PushSettings", () => {
  beforeEach(() => {
    pushMock.support = "supported";
    pushMock.subscription = null;
    (globalThis as { Notification?: unknown }).Notification = { permission: "default" };
  });
  afterEach(cleanup);

  it("iPhone в Safari: подсказка про экран «Домой»", () => {
    pushMock.support = "ios-needs-install";
    apiGet.mockResolvedValue({ enabled: true, public_key: "k" });
    renderIt();
    expect(screen.getByText(/На экран „Домой“/)).toBeTruthy();
  });

  it("на сервере нет ключей — остаётся прежняя кнопка", async () => {
    apiGet.mockResolvedValue({ enabled: false, public_key: null });
    renderIt();
    await waitFor(() => expect(screen.getByText("старая кнопка для компьютера")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Включить" })).toBeNull();
  });

  it("push готов, устройство не подписано — «Включить»", async () => {
    apiGet.mockResolvedValue({ enabled: true, public_key: "k" });
    renderIt();
    await waitFor(() => expect(screen.getByRole("button", { name: "Включить" })).toBeTruthy());
    expect(screen.queryByText("старая кнопка для компьютера")).toBeNull();
  });

  it("устройство уже подписано — «Проверить» и «Выключить»", async () => {
    pushMock.subscription = { endpoint: "https://fcm.googleapis.com/x" };
    apiGet.mockResolvedValue({ enabled: true, public_key: "k" });
    renderIt();
    await waitFor(() => expect(screen.getByRole("button", { name: "Проверить" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "Выключить" })).toBeTruthy();
  });
});
