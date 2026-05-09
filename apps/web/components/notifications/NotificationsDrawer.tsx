"use client";

import { Fragment, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { X, Check, BellOff, RefreshCw, ArrowRight } from "lucide-react";
import {
  useDismissNotification,
  useMarkAllRead,
  useMarkRead,
  useNotificationsList,
} from "@/lib/hooks/use-notifications";
import { relativeTime } from "@/lib/relative-time";
import type { NotificationOut } from "@/lib/types";

const KIND_LABEL: Record<string, string> = {
  lead_transferred: "Передача",
  enrichment_done: "AI Brief",
  enrichment_failed: "Ошибка AI",
  daily_plan_ready: "План дня",
  followup_due: "Напоминание",
  mention: "Упоминание",
  system: "Система",
};

const KIND_STYLE: Record<string, string> = {
  lead_transferred: "bg-accent/10 text-accent",
  enrichment_done: "bg-success/10 text-success",
  enrichment_failed: "bg-rose/10 text-rose",
  daily_plan_ready: "bg-accent/10 text-accent",
  followup_due: "bg-warning/10 text-warning",
  mention: "bg-accent/10 text-accent",
  system: "bg-black/5 text-muted",
};

interface Props {
  open: boolean;
  onClose: () => void;
}

// Sprint 2.5 G2: group drawer items by day («Сегодня» / «Вчера» /
// «D MMM» Russian locale). Native Intl is enough — no date-fns/dayjs
// dependency needed (the drawer wasn't using one before either).
const _RU_MONTH_FORMAT = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
});

function _ymdLocal(d: Date): string {
  // Local date YYYY-MM-DD — used as the group key. Local (not UTC)
  // because the manager's «сегодня» is whatever timezone they're in,
  // not server UTC.
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function _dayHeader(rowDate: Date, today: Date): string {
  const rowKey = _ymdLocal(rowDate);
  const todayKey = _ymdLocal(today);
  if (rowKey === todayKey) return "Сегодня";
  const yest = new Date(today);
  yest.setDate(today.getDate() - 1);
  if (rowKey === _ymdLocal(yest)) return "Вчера";
  return _RU_MONTH_FORMAT.format(rowDate);
}

interface NotifGroup {
  key: string;
  header: string;
  items: NotificationOut[];
}

function groupByDay(items: NotificationOut[]): NotifGroup[] {
  const today = new Date();
  const groups: NotifGroup[] = [];
  for (const n of items) {
    const d = new Date(n.created_at);
    const key = _ymdLocal(d);
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.items.push(n);
    } else {
      groups.push({ key, header: _dayHeader(d, today), items: [n] });
    }
  }
  return groups;
}

export function NotificationsDrawer({ open, onClose }: Props) {
  const router = useRouter();
  const [unreadOnly, setUnreadOnly] = useState(true);
  const { data, isLoading, isError, refetch, isFetching } =
    useNotificationsList({ unread: unreadOnly });
  const { mutate: markRead } = useMarkRead();
  const { mutate: markAll, isPending: isMarkingAll } = useMarkAllRead();
  const { mutate: dismiss } = useDismissNotification();

  // Esc-to-close
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Sprint 2.4 G5 click split: rows WITH lead_id navigate (and mark
  // read on the way out). Rows WITHOUT lead_id (system /
  // daily_plan_ready) don't navigate from a row click — the user
  // gets explicit Check (mark-read) and X (dismiss) controls instead.
  function handleNavRowClick(n: NotificationOut) {
    if (!n.lead_id) return; // defensive — caller already gates
    if (!n.read_at) {
      markRead(n.id);
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    router.push(`/leads/${n.lead_id}` as any);
    onClose();
  }

  const items = data?.items ?? [];
  const unread = data?.unread ?? 0;

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-30 bg-black/20 backdrop-blur-[1px] transition-opacity duration-200 ${
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={onClose}
        aria-hidden
      />

      {/* Panel */}
      <aside
        className={`fixed top-0 right-0 z-40 h-screen w-[420px] max-w-[92vw] bg-white border-l border-black/5 shadow-soft flex flex-col transition-transform duration-300 ease-soft ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        role="dialog"
        aria-label="Уведомления"
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-black/5 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-extrabold tracking-tight">Уведомления</h2>
            {unread > 0 && (
              <span className="bg-accent text-white text-[10px] font-mono font-bold px-2 py-0.5 rounded-pill tabular-nums">
                {unread}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => refetch()}
              className="p-2 rounded-lg text-muted-3 hover:bg-canvas hover:text-ink transition-colors"
              aria-label="Обновить"
            >
              <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-lg text-muted-3 hover:bg-canvas hover:text-ink transition-colors"
              aria-label="Закрыть"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Filter row */}
        <div className="px-5 py-3 border-b border-black/5 flex items-center justify-between gap-2">
          <div className="flex items-center gap-1 bg-canvas rounded-pill p-0.5">
            <button
              onClick={() => setUnreadOnly(true)}
              className={`px-3 py-1 text-[11px] font-semibold rounded-pill transition-colors ${
                unreadOnly ? "bg-white text-ink shadow-soft" : "text-muted-2 hover:text-ink"
              }`}
            >
              Непрочитанные
            </button>
            <button
              onClick={() => setUnreadOnly(false)}
              className={`px-3 py-1 text-[11px] font-semibold rounded-pill transition-colors ${
                !unreadOnly ? "bg-white text-ink shadow-soft" : "text-muted-2 hover:text-ink"
              }`}
            >
              Все
            </button>
          </div>
          <button
            onClick={() => markAll()}
            disabled={unread === 0 || isMarkingAll}
            className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-muted hover:text-accent transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Check size={12} />
            Прочитать все
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {isLoading && (
            <div className="p-5 space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="animate-pulse h-16 bg-canvas rounded-xl border border-black/5"
                />
              ))}
            </div>
          )}

          {isError && (
            <div className="p-8 text-center text-rose text-sm">
              Не удалось загрузить уведомления
            </div>
          )}

          {!isLoading && !isError && items.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
              <BellOff size={28} className="text-muted-3 mb-3" />
              <p className="text-sm font-semibold text-ink mb-1">
                {unreadOnly ? "Всё прочитано" : "Уведомлений пока нет"}
              </p>
              <p className="text-xs text-muted-2">
                {unreadOnly
                  ? "Когда появятся новые события, они окажутся здесь."
                  : "Передачи лидов, готовые AI-бриф и напоминания появятся в этом списке."}
              </p>
            </div>
          )}

          {!isLoading && !isError && items.length > 0 && (
            <ul className="divide-y divide-black/5">
              {groupByDay(items).map((group) => (
                <Fragment key={group.key}>
                  <li
                    className="bg-canvas/60 px-5 py-1.5 sticky top-0 z-10 border-b border-black/5"
                    role="presentation"
                  >
                    <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-3 font-semibold">
                      {group.header}
                    </span>
                  </li>
                  {group.items.map((n) => {
                const kindLabel = KIND_LABEL[n.kind] ?? n.kind;
                const kindStyle = KIND_STYLE[n.kind] ?? "bg-black/5 text-muted";
                const isUnread = n.read_at == null;
                const isNavigable = !!n.lead_id;

                // Body content used by both branches — keeps the
                // unread dot + meta + title/body identical regardless
                // of whether the row is a button or a static block.
                const body = (
                  <div className="flex items-start gap-3">
                    <div className="pt-1.5 shrink-0">
                      <div
                        className={`w-2 h-2 rounded-full ${
                          isUnread ? "bg-accent" : "bg-transparent"
                        }`}
                      />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span
                          className={`font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${kindStyle}`}
                        >
                          {kindLabel}
                        </span>
                        <span className="font-mono text-[10px] text-muted-3">
                          {relativeTime(n.created_at)}
                        </span>
                      </div>
                      <p
                        className={`text-sm leading-snug truncate ${
                          isUnread ? "font-semibold text-ink" : "text-muted"
                        }`}
                      >
                        {n.title}
                      </p>
                      {n.body && (
                        <p className="text-xs text-muted-2 truncate mt-0.5">
                          {n.body}
                        </p>
                      )}
                    </div>

                    {isNavigable && (
                      <ArrowRight
                        size={14}
                        className="text-muted-3 shrink-0 mt-1"
                      />
                    )}
                  </div>
                );

                // Navigable rows (lead_id set) — entire row click goes
                // to the lead; preserves the pre-G5 behaviour.
                if (isNavigable) {
                  return (
                    <li key={n.id}>
                      <button
                        onClick={() => handleNavRowClick(n)}
                        className={`w-full text-left px-5 py-3 transition-colors hover:bg-canvas ${
                          isUnread ? "bg-accent/[0.02]" : ""
                        }`}
                      >
                        {body}
                      </button>
                    </li>
                  );
                }

                // System / daily_plan_ready rows — no navigation.
                // Persistent Check icon marks-read; X (visible on hover)
                // dismisses permanently. The outer <div> intentionally
                // is NOT a button — it shouldn't trap focus or look
                // clickable when it doesn't navigate.
                return (
                  <li
                    key={n.id}
                    className={`group relative px-5 py-3 transition-colors hover:bg-canvas ${
                      isUnread ? "bg-accent/[0.02]" : ""
                    }`}
                  >
                    {body}

                    {/* Action cluster — sits in the trailing edge.
                        Check is always visible; X fades in on hover. */}
                    <div className="absolute top-3 right-4 flex items-center gap-1">
                      {isUnread && (
                        <button
                          type="button"
                          onClick={() => markRead(n.id)}
                          className="p-1.5 rounded-md text-muted-3 hover:bg-success/10 hover:text-success transition-colors"
                          aria-label="Прочитано"
                          title="Отметить прочитанным"
                        >
                          <Check size={13} />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => dismiss(n.id)}
                        className="p-1.5 rounded-md text-muted-3 opacity-0 group-hover:opacity-100 hover:bg-rose/10 hover:text-rose transition-all"
                        aria-label="Скрыть"
                        title="Удалить уведомление"
                      >
                        <X size={13} />
                      </button>
                    </div>
                  </li>
                );
              })}
                </Fragment>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
