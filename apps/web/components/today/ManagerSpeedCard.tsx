"use client";
// «Скорость обработки» on the head/admin /today: per manager, today and this
// week. Web requests count until the first comment; leads a manager created
// count until the first comment after 30 minutes (the note of the call that
// made them a lead is not handling). Leads handed out from the base are left
// out. Time is shown in working hours (Mon–Fri 9–19 MSK), calendar hours aside.
// Data: GET /company/manager-speed.
//
// One row per manager so the team compares at a glance; each cell: speed
// coloured by threshold, a handled / hanging bar, the hanging pill that opens
// the oldest leads, and (week) a mini chart by day.
import { useState, type ReactNode } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, Clock, Globe, Info, UserPlus } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { C } from "@/lib/design-system";
import { useCompanyManagerSpeed } from "@/lib/hooks/use-company";
import { formatWait } from "@/components/today/ReactionCard";
import type { HangingLead, ManagerSpeedRow, SpeedDay, SpeedStats } from "@/lib/types";

type Period = "today" | "week";
type Kind = "form" | "own";

const PERIODS: { key: Period; label: string }[] = [
  { key: "today", label: "Сегодня" },
  { key: "week", label: "Неделя" },
];

// Пороги в рабочих часах: до часа — хорошо, до четырёх — терпимо, дальше — плохо.
const FAST_HOURS = 1;
const SLOW_HOURS = 4;

export function speedTone(workHours: number): "success" | "warning" | "rose" {
  if (workHours <= FAST_HOURS) return "success";
  if (workHours <= SLOW_HOURS) return "warning";
  return "rose";
}

const TONE_TEXT = { success: "text-success", warning: "text-warning", rose: "text-rose" } as const;
const TONE_BG = { success: "bg-success", warning: "bg-warning", rose: "bg-rose" } as const;

// A request that came at night and was answered before 9:00 took zero working
// hours — say so instead of rounding up to «1 мин».
function fmt(hours: number): string {
  return hours === 0 ? "0 мин" : formatWait(hours);
}

function hangingWord(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? "висит" : "висят";
}

export function ManagerSpeedCard() {
  const { data, isLoading, isError } = useCompanyManagerSpeed();
  const [period, setPeriod] = useState<Period>("week");
  const [rulesOpen, setRulesOpen] = useState(false);

  return (
    <Card className="mb-5">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="type-card-title text-brand-primary">Скорость обработки</h3>
            <button
              type="button"
              onClick={() => setRulesOpen((v) => !v)}
              aria-expanded={rulesOpen}
              aria-label="Как считается"
              className={`w-7 h-7 inline-flex items-center justify-center rounded-full text-brand-muted hover:bg-brand-panel transition-colors ${C.focusRing}`}
            >
              <Info size={16} aria-hidden />
            </button>
          </div>
          <p className="type-hint not-italic text-brand-muted">Как быстро менеджеры берут лиды в работу</p>
        </div>
        <div
          className="inline-flex self-start bg-brand-panel rounded-full p-1 gap-0.5"
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

      {rulesOpen && (
        <div className="mb-4 rounded-lg bg-brand-bg p-4 type-body text-brand-muted-strong space-y-1">
          <p>Заявка с сайта — от прихода до первого комментария.</p>
          <p>Свой лид — до первого комментария позже чем через 30 минут: запись первого разговора не в счёт.</p>
          <p>Крупно — рабочие часы (пн–пт 9–19 по Москве), мелко — по календарю. Лиды, выданные из базы, не считаются.</p>
        </div>
      )}

      {isError ? (
        <p className="type-body text-rose py-6 text-center">Не удалось загрузить — обновите страницу.</p>
      ) : isLoading || !data ? (
        <div className="h-24 rounded-lg bg-brand-panel animate-pulse" aria-hidden />
      ) : data.managers.length === 0 ? (
        <p className="type-body text-brand-muted py-6 text-center">
          На этой неделе новых заявок с сайта и своих лидов нет.
        </p>
      ) : (
        <div>
          <div className="hidden md:grid md:grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)] gap-6 pb-2">
            <span />
            <ColumnHead icon={<Globe size={14} aria-hidden />} label="Заявки с сайта" />
            <ColumnHead icon={<UserPlus size={14} aria-hidden />} label="Свои лиды" />
          </div>
          {data.managers.map((m) => (
            <ManagerRow key={m.manager_id} row={m} period={period} />
          ))}
          <Legend />
        </div>
      )}
    </Card>
  );
}

function ColumnHead({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-2 type-caption text-brand-muted">
      {icon}
      {label}
    </span>
  );
}

function ManagerRow({ row, period }: { row: ManagerSpeedRow; period: Period }) {
  const [open, setOpen] = useState<Kind | null>(null);
  const stats = row[period];
  const list = open && period === "week" ? row.hanging.filter((h) => h.kind === open) : [];

  return (
    <section aria-label={row.name} className="border-t border-brand-border py-4">
      <div className="grid grid-cols-1 md:grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)] gap-4 md:gap-6 md:items-start">
        <div className="flex items-center gap-3">
          <span
            className="w-8 h-8 shrink-0 rounded-full bg-brand-soft text-brand-accent-text inline-flex items-center justify-center type-label"
            aria-hidden
          >
            {(row.name[0] ?? "?").toUpperCase()}
          </span>
          <span className="type-body font-semibold text-brand-primary truncate">{row.name}</span>
        </div>
        <SpeedCell
          kind="form"
          stats={stats.forms}
          days={period === "week" ? row.days : null}
          open={open === "form"}
          canOpen={period === "week" && row.hanging.some((h) => h.kind === "form")}
          onToggle={() => setOpen((v) => (v === "form" ? null : "form"))}
        />
        <SpeedCell
          kind="own"
          stats={stats.own}
          days={period === "week" ? row.days : null}
          open={open === "own"}
          canOpen={period === "week" && row.hanging.some((h) => h.kind === "own")}
          onToggle={() => setOpen((v) => (v === "own" ? null : "own"))}
        />
      </div>
      {list.length > 0 && <HangingList items={list} />}
    </section>
  );
}

function SpeedCell({
  kind,
  stats,
  days,
  open,
  canOpen,
  onToggle,
}: {
  kind: Kind;
  stats: SpeedStats;
  days: SpeedDay[] | null;
  open: boolean;
  canOpen: boolean;
  onToggle: () => void;
}) {
  const label = kind === "form" ? "Заявки с сайта" : "Свои лиды";
  const handledPct = stats.total > 0 ? (stats.handled / stats.total) * 100 : 0;
  const hangingPct = stats.total > 0 ? (stats.hanging / stats.total) * 100 : 0;

  return (
    <div className="min-w-0">
      <span className="md:hidden inline-flex items-center gap-2 type-caption text-brand-muted mb-1">
        {kind === "form" ? <Globe size={14} aria-hidden /> : <UserPlus size={14} aria-hidden />}
        {label}
      </span>

      {stats.total === 0 ? (
        <p className="type-body text-brand-muted">нет новых</p>
      ) : (
        <>
          <div className="flex items-center gap-3 min-w-0">
            {stats.median_work_hours != null ? (
              <span
                className={`inline-flex items-center gap-1 type-kpi-number ${TONE_TEXT[speedTone(stats.median_work_hours)]}`}
              >
                <Clock size={16} aria-hidden />
                {fmt(stats.median_work_hours)}
              </span>
            ) : (
              <span className="type-body text-brand-muted">ещё никого не обработал</span>
            )}
            {stats.median_hours != null && (
              <span className="type-hint not-italic text-brand-muted tabular-nums">
                {fmt(stats.median_hours)} по календарю
              </span>
            )}
            {days && <DayBars days={days} kind={kind} />}
          </div>

          <div
            className="mt-2 mb-2 flex h-1.5 rounded-full overflow-hidden bg-brand-panel"
            role="img"
            aria-label={`обработано ${stats.handled} из ${stats.total}, ${hangingWord(stats.hanging)} ${stats.hanging}`}
          >
            <span className="bg-success" style={{ width: `${handledPct}%` }} />
            <span className="bg-rose/60" style={{ width: `${hangingPct}%` }} />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="type-hint not-italic text-brand-muted tabular-nums">
              {stats.handled} из {stats.total} обработано
            </span>
            {stats.hanging > 0 ? (
              canOpen ? (
                <button
                  type="button"
                  onClick={onToggle}
                  aria-expanded={open}
                  className={`inline-flex items-center gap-1 h-6 px-3 rounded-full bg-rose/10 text-rose type-label tabular-nums hover:bg-rose/15 transition-colors ${C.focusRing}`}
                >
                  {stats.hanging} {hangingWord(stats.hanging)}
                  {open ? <ChevronDown size={12} aria-hidden /> : <ChevronRight size={12} aria-hidden />}
                </button>
              ) : (
                <span className="inline-flex items-center h-6 px-3 rounded-full bg-rose/10 text-rose type-label tabular-nums">
                  {stats.hanging} {hangingWord(stats.hanging)}
                </span>
              )
            ) : (
              stats.handled > 0 && <span className="type-hint not-italic text-success">все в работе</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

const WEEKDAY = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

/** Mini chart: median working hours per day of the week, by threshold colour.
 *  A low grey stub = nobody was handled that day. */
function DayBars({ days, kind }: { days: SpeedDay[]; kind: Kind }) {
  const values = days.map((d) => (kind === "form" ? d.forms : d.own));
  if (values.every((v) => v == null)) return null;
  const max = Math.max(SLOW_HOURS, ...values.map((v) => v ?? 0));
  return (
    <span className="ml-auto inline-flex items-end gap-1 h-6 shrink-0" aria-label="по дням недели">
      {days.map((d, i) => {
        const v = values[i];
        const weekday = WEEKDAY[new Date(`${d.day}T12:00:00`).getDay()];
        return (
          <span
            key={d.day}
            title={v == null ? `${weekday}: нет обработанных` : `${weekday}: ${fmt(v)}`}
            className={`w-1.5 rounded-sm ${v == null ? "bg-brand-panel" : TONE_BG[speedTone(v)]}`}
            style={{ height: v == null ? "4px" : `${Math.max(16, (v / max) * 100)}%` }}
          />
        );
      })}
    </span>
  );
}

function HangingList({ items }: { items: HangingLead[] }) {
  return (
    <ul className="mt-3 rounded-lg bg-brand-bg px-4 py-1">
      {items.map((h) => (
        <li key={h.lead_id} className="border-t border-brand-border first:border-t-0">
          <Link
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            href={`/leads/${h.lead_id}` as any}
            className={`flex items-center gap-3 py-2 rounded-md hover:bg-white transition-colors ${C.focusRing}`}
          >
            <span className="flex-1 min-w-0 truncate type-body text-brand-primary">{h.company_name}</span>
            <span className="shrink-0 type-label tabular-nums text-rose">висит {formatWait(h.hours)}</span>
            <ChevronRight size={16} className="shrink-0 text-brand-muted" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Legend() {
  const items = [
    { tone: "success" as const, label: "до 1 рабочего часа" },
    { tone: "warning" as const, label: "до 4 часов" },
    { tone: "rose" as const, label: "дольше" },
  ];
  return (
    <div className="border-t border-brand-border pt-3 flex flex-wrap gap-4">
      {items.map((it) => (
        <span key={it.tone} className="inline-flex items-center gap-2 type-hint not-italic text-brand-muted">
          <span className={`w-2 h-2 rounded-full ${TONE_BG[it.tone]}`} aria-hidden />
          {it.label}
        </span>
      ))}
    </div>
  );
}
