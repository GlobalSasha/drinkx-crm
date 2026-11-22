"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import {
  currentSubscription,
  detectPushSupport,
  disablePush,
  enablePush,
  readPushEnv,
  type PushConfig,
  type PushSupport,
} from "@/lib/push";

type Status = "checking" | "off" | "on" | "denied" | "error";

const BTN_PRIMARY =
  "shrink-0 px-3 py-1.5 text-xs font-semibold rounded-full bg-brand-accent text-white transition-colors disabled:opacity-50";
const BTN_GHOST =
  "shrink-0 px-3 py-1.5 text-xs font-semibold rounded-full border border-brand-border text-brand-primary transition-colors disabled:opacity-50";

/**
 * «Уведомления на этом устройстве» at the top of the bell drawer.
 * Push (works with the CRM closed) when the device and the server allow it;
 * on an iPhone in a Safari tab — how to add the CRM to the home screen;
 * otherwise falls back to `children` (the in-tab desktop pop-ups).
 */
export function PushSettings({ children }: { children?: ReactNode }) {
  const [support, setSupport] = useState<PushSupport>("unsupported");
  const [status, setStatus] = useState<Status>("checking");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const config = useQuery({
    queryKey: ["notifications", "push-config"],
    queryFn: () => api.get<PushConfig>("/notifications/push/config"),
    staleTime: 10 * 60 * 1000,
  });

  useEffect(() => {
    const s = detectPushSupport(readPushEnv());
    setSupport(s);
    if (s !== "supported") return;
    if (Notification.permission === "denied") {
      setStatus("denied");
      return;
    }
    currentSubscription()
      .then((sub) => setStatus(sub ? "on" : "off"))
      .catch(() => setStatus("off"));
  }, []);

  if (support === "ios-needs-install") {
    return (
      <Row>
        <p className="text-xs text-brand-muted">
          Чтобы заявки и письма приходили на iPhone, даже когда CRM закрыта: нажмите
          «Поделиться» → «На экран „Домой“», откройте CRM с новой иконки и включите
          уведомления здесь.
        </p>
      </Row>
    );
  }

  const pushReady = support === "supported" && config.data?.enabled;
  if (!pushReady) return <>{children}</>;

  async function turnOn() {
    if (!config.data) return;
    setBusy(true);
    setNote(null);
    const result = await enablePush(config.data);
    setStatus(result === "on" ? "on" : result);
    if (result === "error") setNote("Не получилось включить. Попробуйте ещё раз.");
    setBusy(false);
  }

  async function turnOff() {
    setBusy(true);
    setNote(null);
    try {
      await disablePush();
      setStatus("off");
    } catch {
      setNote("Не получилось выключить. Попробуйте ещё раз.");
    }
    setBusy(false);
  }

  async function test() {
    setBusy(true);
    setNote(null);
    try {
      const r = await api.post<{ sent: number }>("/notifications/push/test");
      setNote(r.sent > 0 ? "Отправили — уведомление придёт через несколько секунд." : "Это устройство не найдено, включите заново.");
      if (r.sent === 0) setStatus("off");
    } catch {
      setNote("Не получилось отправить проверку.");
    }
    setBusy(false);
  }

  if (status === "checking") return null;

  if (status === "denied") {
    return (
      <Row>
        <p className="text-xs text-brand-muted">
          Уведомления запрещены в настройках браузера или телефона для этого сайта.
        </p>
      </Row>
    );
  }

  if (status === "on") {
    return (
      <Row>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-brand-muted">
            Уведомления на этом устройстве включены — придут, даже когда CRM закрыта
          </p>
          <div className="flex gap-1">
            <button onClick={() => void test()} disabled={busy} className={BTN_GHOST}>
              Проверить
            </button>
            <button onClick={() => void turnOff()} disabled={busy} className={BTN_GHOST}>
              Выключить
            </button>
          </div>
        </div>
        {note && <p className="text-xs text-brand-muted mt-2">{note}</p>}
      </Row>
    );
  }

  return (
    <Row tinted>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-brand-muted">
          Получать новые заявки и письма на это устройство, даже когда CRM закрыта
        </p>
        <button onClick={() => void turnOn()} disabled={busy} className={BTN_PRIMARY}>
          Включить
        </button>
      </div>
      {note && <p className="text-xs text-rose mt-2">{note}</p>}
    </Row>
  );
}

function Row({ children, tinted }: { children: ReactNode; tinted?: boolean }) {
  return (
    <div className={`px-5 py-3 border-b border-brand-border ${tinted ? "bg-brand-soft/40" : ""}`}>
      {children}
    </div>
  );
}
