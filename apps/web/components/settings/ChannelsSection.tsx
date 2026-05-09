"use client";
// ChannelsSection — Sprint 2.4 G2.
//
// Read-only view over the workspace's outbound + inbound channels:
//   - Gmail: per-user OAuth status + «Подключить» CTA that initiates
//     the existing Sprint 2.0 OAuth flow.
//   - SMTP: workspace config from env vars. Read-only in v1 — editing
//     SMTP is via env vars on the host (Sprint 2.4 NOT-ALLOWED:
//     «DB-backed SMTP credentials» — would require credentials-at-rest
//     story we're not shipping this sprint).
import { AlertCircle, CheckCircle2, Loader2, Mail, Send } from "lucide-react";

import { ApiError } from "@/lib/api-client";
import { useChannelsStatus } from "@/lib/hooks/use-channels";
import { useConnectGmail } from "@/lib/hooks/use-inbox";

function formatRelative(iso: string | null): string {
  if (!iso) return "никогда";
  const t = new Date(iso).getTime();
  const ago = Date.now() - t;
  if (ago < 60_000) return "только что";
  const m = Math.round(ago / 60_000);
  if (m < 60) return `${m} мин назад`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} ч назад`;
  const d = Math.round(h / 24);
  return `${d} дн назад`;
}

export function ChannelsSection() {
  const statusQuery = useChannelsStatus();
  const connect = useConnectGmail();

  if (statusQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }

  if (statusQuery.isError || !statusQuery.data) {
    return (
      <p className="text-sm text-rose py-8 text-center">
        Не удалось загрузить состояние каналов.
      </p>
    );
  }

  const { gmail, smtp } = statusQuery.data;

  function handleConnectGmail() {
    connect.mutate(undefined, {
      onSuccess: ({ redirect_url }) => {
        // Same-window redirect — Google's consent flow needs the
        // top-level navigation, can't be done in an <iframe>.
        window.location.assign(redirect_url);
      },
      onError: (err: ApiError) => {
        // Backend returns 503 «Gmail not configured» when
        // GOOGLE_CLIENT_ID is empty in env. The card already shows
        // «not configured» state; a toast would be redundant — silent
        // here is fine.
        console.warn("Gmail connect failed:", err.status, err.body);
      },
    });
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-extrabold tracking-tight">Каналы</h2>
        <p className="text-xs text-muted-2 mt-0.5">
          Входящие письма из Gmail и исходящая почта через SMTP.
          В v1 настройки только просмотр; правки — через переменные
          окружения на сервере.
        </p>
      </div>

      {/* Gmail card */}
      <div className="bg-white border border-black/5 rounded-2xl shadow-soft p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-canvas flex items-center justify-center shrink-0">
              <Mail size={18} className="text-muted" />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-extrabold text-ink">Gmail</h3>
              <p className="text-xs text-muted-2 mt-0.5">
                Письма автоматически попадают в /inbox для разбора и
                привязки к лидам (Sprint 2.0).
              </p>
              {/* Status row */}
              <div className="mt-2.5 flex items-center gap-1.5">
                {!gmail.configured ? (
                  <>
                    <AlertCircle size={13} className="text-warning shrink-0" />
                    <span className="text-xs text-warning font-semibold">
                      Не настроен
                    </span>
                    <span className="text-xs text-muted-3">
                      · GOOGLE_CLIENT_ID не указан в env
                    </span>
                  </>
                ) : gmail.connected ? (
                  <>
                    <CheckCircle2 size={13} className="text-success shrink-0" />
                    <span className="text-xs text-success font-semibold">
                      Подключено
                    </span>
                    <span className="text-xs text-muted-3 font-mono">
                      · Последняя синхронизация:{" "}
                      {formatRelative(gmail.last_sync_at)}
                    </span>
                  </>
                ) : (
                  <>
                    <AlertCircle size={13} className="text-muted-2 shrink-0" />
                    <span className="text-xs text-muted font-semibold">
                      Не подключено
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="shrink-0">
            {gmail.configured && !gmail.connected && (
              <button
                onClick={handleConnectGmail}
                disabled={connect.isPending}
                className="inline-flex items-center gap-1.5 bg-ink text-white rounded-pill px-4 py-2 text-sm font-semibold hover:bg-ink/90 disabled:opacity-40 active:scale-[0.98] transition-all duration-300"
              >
                {connect.isPending ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Mail size={13} />
                )}
                Подключить Gmail
              </button>
            )}
            {gmail.configured && gmail.connected && (
              <button
                onClick={handleConnectGmail}
                disabled={connect.isPending}
                className="inline-flex items-center gap-1.5 bg-canvas text-ink border border-black/10 rounded-pill px-3 py-1.5 text-xs font-semibold hover:bg-canvas-2 hover:border-black/20 disabled:opacity-40 transition-all duration-300"
              >
                Переподключить
              </button>
            )}
          </div>
        </div>
      </div>

      {/* SMTP card */}
      <div className="bg-white border border-black/5 rounded-2xl shadow-soft p-5">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-canvas flex items-center justify-center shrink-0">
            <Send size={18} className="text-muted" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-extrabold text-ink">
                SMTP (исходящая почта)
              </h3>
              {smtp.configured ? (
                <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wide bg-success/10 text-success rounded-pill px-2 py-0.5">
                  <CheckCircle2 size={10} />
                  активен
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wide bg-warning/10 text-warning rounded-pill px-2 py-0.5">
                  <AlertCircle size={10} />
                  stub-режим
                </span>
              )}
            </div>
            <p className="text-xs text-muted-2 mt-0.5">
              {smtp.configured
                ? "Используется ежедневной email-сводкой и системными уведомлениями."
                : "SMTP_HOST пустой — письма пишутся в логи воркера, не отправляются. Настройте на сервере, затем перезапустите."}
            </p>

            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <Field label="Хост" value={smtp.host || "—"} mono />
              <Field label="Порт" value={String(smtp.port)} mono />
              <Field label="От кого" value={smtp.from_address} mono />
              <Field label="Пользователь" value={smtp.user || "—"} mono />
            </div>

            <p className="text-[11px] text-muted-3 mt-3 leading-tight">
              Правка SMTP — через переменные окружения на сервере
              (SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD /
              SMTP_FROM). Из UI пока не настраивается — credentials-at-rest
              запланирован на Sprint 2.5+.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-[10px] font-mono uppercase tracking-wide text-muted-3 shrink-0">
        {label}:
      </span>
      <span
        className={`${
          mono ? "font-mono" : ""
        } text-xs text-ink truncate`}
        title={value}
      >
        {value}
      </span>
    </div>
  );
}
