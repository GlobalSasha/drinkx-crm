"use client";

// CEO /today — панель работы менеджеров. «Труд ↔ результат»: сколько менеджер
// реально работал в CRM (активное время) и что с его лидами. Один переключатель
// периода (день/неделя/месяц) — единственный источник правды, гонит один запрос.
// 1 менеджер → большая карточка-спотлайт; много → таблица-строки с сортировкой.
// Старый обзор потока заявок — свёрнутой секцией внизу.

import { useMemo, useState } from "react";
import Link from "next/link";
import { Clock, ChevronRight, ArrowDown, ArrowUp } from "lucide-react";

import { pageContainerVariants } from "@/components/ui/PageContainer";
import { C } from "@/lib/design-system";
import { useCompanyManagers } from "@/lib/hooks/use-company";
import { relativeTime } from "@/lib/relative-time";
import type { ManagerRow, ManagerPeriod, ManagerAlert } from "@/lib/types";
import { LeadFlowBody } from "@/components/today/CeoOverview";

const PERIODS: { key: ManagerPeriod; label: string }[] = [
  { key: "day", label: "Сегодня" },
  { key: "week", label: "Неделя" },
  { key: "month", label: "Месяц" },
];

// ── helpers ─────────────────────────────────────────────────────────
function fmtMinutes(total: number): string {
  if (!total || total <= 0) return "0м";
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m}м`;
  if (m === 0) return `${h}ч`;
  return `${h}ч ${String(m).padStart(2, "0")}м`;
}

function periodCaption(p: ManagerPeriod): string {
  return p === "day" ? "сегодня" : p === "week" ? "за неделю" : "за месяц";
}

function lastActiveText(iso: string | null): string {
  return iso ? relativeTime(iso) : "—";
}

function pluralRu(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] ?? "?").toUpperCase();
}

/** Fill the sparkline to 14 continuous days ending today (UTC keys). */
function fill14(daily: { date: string; minutes: number }[]): number[] {
  const byDate = new Map(daily.map((d) => [d.date, d.minutes]));
  const out: number[] = [];
  const today = new Date();
  for (let i = 13; i >= 0; i--) {
    const d = new Date(today);
    d.setUTCDate(today.getUTCDate() - i);
    out.push(byDate.get(d.toISOString().slice(0, 10)) ?? 0);
  }
  return out;
}

function alertText(a: ManagerAlert): string {
  if (a.type === "silent") {
    const d = a.days ?? 0;
    return `${a.name} не заходил ${d} ${pluralRu(d, "день", "дня", "дней")}`;
  }
  const c = a.count ?? 0;
  return `${c} ${pluralRu(c, "лид", "лида", "лидов")} застряли 7+ дней у ${a.name}`;
}

// ── page ────────────────────────────────────────────────────────────
export function TeamOverview() {
  const [period, setPeriod] = useState<ManagerPeriod>("week");
  const { data, isLoading, isError } = useCompanyManagers(period);
  const managers = data?.managers ?? [];

  const dateCaption = useMemo(() => {
    const d = new Date();
    const weekday = d.toLocaleDateString("ru-RU", { weekday: "long" });
    const date = d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
    const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    return `${weekday}, ${date} · ${time}`;
  }, []);

  return (
    <div className={pageContainerVariants({ surface: "data" })}>
      {/* Header + period toggle */}
      <div className="bg-white border border-brand-border rounded-card p-6 mb-5">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <div className="type-caption text-brand-muted">{dateCaption}</div>
            <h1 className={`type-page-title ${C.color.text} mt-1`}>Команда</h1>
            <p className={`type-caption ${C.color.mutedLight} mt-1`}>
              Кто сколько работает и что с их лидами
            </p>
          </div>
          <div
            className="inline-flex self-start sm:self-auto bg-brand-panel rounded-full p-1 gap-0.5"
            role="tablist"
            aria-label="Период"
          >
            {PERIODS.map((p) => (
              <button
                key={p.key}
                type="button"
                role="tab"
                aria-selected={period === p.key}
                onClick={() => setPeriod(p.key)}
                className={`px-4 py-1.5 rounded-full type-button transition-colors ${C.focusRing} ${
                  period === p.key
                    ? "bg-white text-brand-primary shadow-sm"
                    : "text-brand-muted hover:text-brand-primary"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <AlertsStrip alerts={data?.alerts} />

      {isError ? (
        <div className="rounded-card border border-rose/20 bg-rose/5 p-6">
          <p className="type-card-title text-rose">Не удалось загрузить данные</p>
          <p className="type-body text-brand-muted mt-1">
            Обновите страницу — данные временно недоступны.
          </p>
        </div>
      ) : isLoading ? (
        <div className="bg-white border border-brand-border rounded-card p-7 space-y-4">
          <div className="h-11 w-40 rounded-lg bg-brand-panel animate-pulse" />
          <div className="h-9 w-full rounded-lg bg-brand-panel animate-pulse" />
          <div className="h-9 w-full rounded-lg bg-brand-panel animate-pulse" />
        </div>
      ) : managers.length === 0 ? (
        <div className="bg-white border border-brand-border rounded-card p-10 text-center">
          <p className="type-card-title text-brand-primary">Пока нет менеджеров</p>
          <p className="type-body text-brand-muted mt-1">
            Добавьте менеджеров в команду — и здесь появится их работа и результаты.
          </p>
          <Link
            href="/team"
            className={`inline-flex items-center gap-1 mt-4 type-button text-brand-accent-text hover:underline ${C.focusRing}`}
          >
            Перейти в команду <ChevronRight size={14} />
          </Link>
        </div>
      ) : managers.length === 1 ? (
        <Spotlight m={managers[0]} period={period} />
      ) : (
        <ManagerTable managers={managers} />
      )}

      <p className="type-hint text-brand-muted text-center mt-4 px-4">
        «Активное время» — минуты реальной работы (мышь / клавиши / переходы), а не «вкладка
        открыта». Замер копится с момента запуска.
      </p>

      <FlowSection />
    </div>
  );
}

// ── alerts ──────────────────────────────────────────────────────────
function AlertsStrip({ alerts }: { alerts?: ManagerAlert[] }) {
  if (!alerts || alerts.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 mb-5">
      {alerts.map((a, i) => (
        <span
          key={`${a.type}-${a.user_id}-${i}`}
          className="inline-flex items-center gap-2 rounded-full bg-brand-soft border border-brand-accent/15 px-4 py-2 type-label text-brand-accent-text"
        >
          <span
            className={`size-1.5 rounded-full shrink-0 ${a.type === "silent" ? "bg-warning" : "bg-rose"}`}
            aria-hidden
          />
          {alertText(a)}
        </span>
      ))}
    </div>
  );
}

// ── spotlight (1 manager) ───────────────────────────────────────────
function Spotlight({ m, period }: { m: ManagerRow; period: ManagerPeriod }) {
  const spark = fill14(m.active_daily);
  const sparkMax = Math.max(1, ...spark);
  return (
    <div className="bg-white border border-brand-border rounded-card p-6 sm:p-7">
      {/* manager header */}
      <div className="flex items-center gap-3.5 mb-6">
        <span className="size-11 shrink-0 rounded-full bg-brand-soft text-brand-accent-text flex items-center justify-center type-card-title">
          {initials(m.name)}
        </span>
        <div className="min-w-0">
          <div className="type-card-title text-brand-primary truncate">{m.name}</div>
          <div className="type-hint not-italic text-brand-muted">Менеджер по продажам</div>
        </div>
        <div className="ml-auto text-right shrink-0">
          <div className="type-caption text-brand-muted">был активен</div>
          <div className="type-label text-success">{lastActiveText(m.last_active_at)}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_1px_1fr] gap-6 md:gap-8">
        {/* ТРУД */}
        <div>
          <ColLabel accent>Труд</ColLabel>
          <div className="mb-4">
            <div className="type-kpi-number-lg tabular-nums text-brand-primary">
              {fmtMinutes(m.active_minutes)}
            </div>
            <div className="type-hint not-italic text-brand-muted mt-1">
              активное время в CRM · {periodCaption(period)}
            </div>
            <div className="flex items-end gap-0.5 h-9 mt-3" aria-hidden>
              {spark.map((v, i) => (
                <span
                  key={i}
                  className={`flex-1 rounded-t-sm ${
                    i === spark.length - 1 ? "bg-brand-accent" : "bg-brand-soft"
                  }`}
                  style={{ height: `${Math.max(8, Math.round((v / sparkMax) * 100))}%` }}
                />
              ))}
            </div>
          </div>
          <div>
            <MetricRow k="Новых лидов добавил" v={m.new_leads} />
            <MetricRow k="Действий всего" v={m.actions} />
            <MetricRow k="КП отправлено" v={m.kp_sent} last />
          </div>
        </div>

        <div className="hidden md:block bg-brand-border" aria-hidden />

        {/* РЕЗУЛЬТАТ */}
        <div>
          <ColLabel>Результат по его лидам</ColLabel>
          <div>
            <MetricRow k="В работе сейчас" v={m.in_work} />
            <MetricRow
              k="Продвинул по воронке"
              v={m.stage_moves}
              suffix={pluralRu(m.stage_moves, "этап", "этапа", "этапов")}
            />
            <MetricRow k="Застряло 7+ дней" v={m.stuck} danger={m.stuck > 0} />
            <MetricRow
              k="Задач закрыто / просрочено"
              v={m.tasks_done}
              suffix={m.tasks_overdue > 0 ? `/ ${m.tasks_overdue} просроч.` : undefined}
              last
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function ColLabel({ children, accent }: { children: React.ReactNode; accent?: boolean }) {
  return (
    <div
      className={`type-table-header mb-4 ${accent ? "text-brand-accent-text" : "text-brand-muted"}`}
    >
      {children}
    </div>
  );
}

function MetricRow({
  k,
  v,
  suffix,
  danger,
  last,
}: {
  k: string;
  v: number | string;
  suffix?: string;
  danger?: boolean;
  last?: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-between gap-3 py-2.5 ${
        last ? "" : "border-b border-brand-bg"
      }`}
    >
      <span className="type-body text-brand-muted-strong">{k}</span>
      <span className="shrink-0 text-right">
        <span
          className={`type-card-title tabular-nums ${danger ? "text-rose" : "text-brand-primary"}`}
        >
          {v}
        </span>
        {suffix && <span className="type-hint not-italic text-brand-muted ml-1">{suffix}</span>}
      </span>
    </div>
  );
}

// ── table (many managers) ───────────────────────────────────────────
type SortKey =
  | "active_minutes"
  | "new_leads"
  | "actions"
  | "stage_moves"
  | "kp_sent"
  | "stuck"
  | "last_active";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "active_minutes", label: "Активн. время" },
  { key: "new_leads", label: "Новых лидов" },
  { key: "actions", label: "Действий" },
  { key: "stage_moves", label: "Двинул этапов" },
  { key: "kp_sent", label: "КП" },
  { key: "stuck", label: "Застряло" },
  { key: "last_active", label: "Был активен" },
];

function ManagerTable({ managers }: { managers: ManagerRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("active_minutes");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    const val = (m: ManagerRow): number =>
      sortKey === "last_active"
        ? m.last_active_at
          ? Date.parse(m.last_active_at)
          : 0
        : (m[sortKey] as number);
    return [...managers].sort((a, b) => (val(a) - val(b)) * (dir === "asc" ? 1 : -1));
  }, [managers, sortKey, dir]);

  const onSort = (k: SortKey) => {
    if (k === sortKey) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setDir("desc");
    }
  };

  return (
    <div className="bg-white border border-brand-border rounded-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse">
          <thead>
            <tr className="border-b border-brand-border">
              <th className="type-table-header text-brand-muted text-left px-5 py-3.5">Менеджер</th>
              {COLUMNS.map((c) => (
                <th key={c.key} className="type-table-header text-brand-muted text-right px-4 py-3.5">
                  <button
                    type="button"
                    onClick={() => onSort(c.key)}
                    className={`inline-flex items-center gap-1 ml-auto hover:text-brand-primary transition-colors ${C.focusRing} ${
                      sortKey === c.key ? "text-brand-primary" : ""
                    }`}
                  >
                    {c.label}
                    {sortKey === c.key &&
                      (dir === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((m) => {
              const silent = m.last_active_at
                ? Date.now() - Date.parse(m.last_active_at) > 48 * 3600_000
                : true;
              return (
                <tr key={m.user_id} className="border-b border-brand-bg last:border-0 hover:bg-brand-bg/60">
                  <td className="px-5 py-4">
                    <Link
                      href={`/team/${m.user_id}` as `/team/${string}`}
                      className={`inline-flex items-center gap-3 group ${C.focusRing}`}
                    >
                      <span className="size-8 shrink-0 rounded-full bg-brand-soft text-brand-accent-text flex items-center justify-center type-label">
                        {initials(m.name)}
                      </span>
                      <span className="min-w-0">
                        <span className="type-body font-semibold text-brand-primary group-hover:underline block truncate">
                          {m.name}
                        </span>
                        <span className="type-hint not-italic text-brand-muted block">Менеджер</span>
                      </span>
                    </Link>
                  </td>
                  <NumCell v={fmtMinutes(m.active_minutes)} danger={m.active_minutes === 0} />
                  <NumCell v={m.new_leads} danger={m.new_leads === 0} />
                  <NumCell v={m.actions} danger={m.actions === 0} />
                  <NumCell v={m.stage_moves} />
                  <NumCell v={m.kp_sent} />
                  <NumCell v={m.stuck} danger={m.stuck > 0} />
                  <td
                    className={`px-4 py-4 text-right type-body tabular-nums whitespace-nowrap ${
                      silent ? "text-rose font-semibold" : "text-brand-muted"
                    }`}
                  >
                    {lastActiveText(m.last_active_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function NumCell({ v, danger }: { v: number | string; danger?: boolean }) {
  return (
    <td
      className={`px-4 py-4 text-right type-card-title tabular-nums ${
        danger ? "text-rose" : "text-brand-primary"
      }`}
    >
      {v}
    </td>
  );
}

// ── collapsed lead-flow section ─────────────────────────────────────
function FlowSection() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-card border border-brand-border bg-white overflow-hidden mt-6">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={`w-full flex items-center justify-between gap-2 px-5 sm:px-6 py-4 ${C.focusRing}`}
      >
        <span className="flex items-center gap-2 type-card-title text-brand-primary">
          <Clock size={16} className="text-brand-muted" />
          Поток заявок
        </span>
        <span className="flex items-center gap-2 type-hint not-italic text-brand-muted">
          источники и конверсия
          <ChevronRight size={16} className={`transition-transform ${open ? "rotate-90" : ""}`} />
        </span>
      </button>
      {open && (
        <div className="px-5 sm:px-6 pb-6 border-t border-brand-border">
          <LeadFlowBody />
        </div>
      )}
    </div>
  );
}
