"use client";

// «Входящие заявки» on the head/admin /today: new leads by day (30) or month
// (12), stacked by source, with a per-source table. Data: GET /company/inflow.
// Every new lead counts; hand-typed leads and file loads share one grey
// «Вручную и загрузка базы» series that can be hidden — a base load spikes a
// single day and would otherwise drown the real inflow.

import { useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  BRAND_CHART_COLORS,
  CHART_AXIS_COLOR,
  CHART_AXIS_LINE_COLOR,
  CHART_GRID_COLOR,
  ChartContainer,
  ChartTooltip,
} from "@/components/ui/Chart";
import { C } from "@/lib/design-system";
import { useCompanyInflow } from "@/lib/hooks/use-company";
import type { CompanyInflow, InflowPoint } from "@/lib/types";

type Mode = "day" | "month";
const DAY_WINDOW = 30;
const MONTH_WINDOW = 12;

// ── date keys (UTC arithmetic on plain YYYY-MM-DD, no timezone drift) ──
function parseKey(key: string): Date {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
function toKey(d: Date): string {
  return d.toISOString().slice(0, 10);
}
function addDays(key: string, n: number): string {
  const d = parseKey(key);
  d.setUTCDate(d.getUTCDate() + n);
  return toKey(d);
}
function monthKey(key: string, back = 0): string {
  const d = parseKey(key);
  return toKey(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - back, 1)));
}
function dayLabel(key: string): string {
  return `${key.slice(8, 10)}.${key.slice(5, 7)}`;
}
function monthLabel(key: string): string {
  const d = parseKey(key);
  const m = d.toLocaleDateString("ru-RU", { month: "short", timeZone: "UTC" }).replace(".", "");
  return d.getUTCMonth() === 0 ? `${m} ${String(d.getUTCFullYear()).slice(2)}` : m;
}

/** source → bucket → count */
function index(points: InflowPoint[]): Map<string, Map<string, number>> {
  const out = new Map<string, Map<string, number>>();
  for (const p of points) {
    const row = out.get(p.source) ?? new Map<string, number>();
    row.set(p.bucket, (row.get(p.bucket) ?? 0) + p.count);
    out.set(p.source, row);
  }
  return out;
}

function sumRange(row: Map<string, number> | undefined, keys: string[]): number {
  if (!row) return 0;
  return keys.reduce((acc, k) => acc + (row.get(k) ?? 0), 0);
}

function pct(cur: number, prev: number): number | null {
  if (prev <= 0) return null;
  return Math.round(((cur - prev) / prev) * 100);
}

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

export function InflowCard() {
  const { data, isLoading, isError } = useCompanyInflow();
  const [mode, setMode] = useState<Mode>("day");
  // null = untouched: the manual/base-load bucket starts hidden, so a single
  // file load doesn't flatten the chart and inflate every delta.
  const [hiddenState, setHidden] = useState<Set<string> | null>(null);
  const hidden = useMemo(
    () => hiddenState ?? new Set((data?.sources ?? []).filter((s) => s.is_manual).map((s) => s.name)),
    [hiddenState, data],
  );

  return (
    <Card className="mb-5">
      <CardHeader>
        <CardTitle>Входящие заявки</CardTitle>
        <div
          className="inline-flex bg-brand-panel rounded-full p-1 gap-0.5"
          role="tablist"
          aria-label="Разрез"
        >
          {(
            [
              ["day", "По дням"],
              ["month", "По месяцам"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={mode === key}
              onClick={() => setMode(key)}
              className={`px-4 py-1.5 rounded-full type-button transition-colors ${C.focusRing} ${
                mode === key ? "bg-white text-brand-primary" : "text-brand-muted hover:text-brand-primary"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </CardHeader>

      {isError ? (
        <p className="type-body text-rose py-6 text-center">Не удалось загрузить заявки — обновите страницу.</p>
      ) : isLoading || !data ? (
        <div className="space-y-3" aria-hidden>
          <div className="h-16 rounded-lg bg-brand-panel animate-pulse" />
          <div className="h-56 rounded-lg bg-brand-panel animate-pulse" />
        </div>
      ) : data.sources.length === 0 ? (
        <p className="type-body text-brand-muted py-6 text-center">За последний год новых заявок нет.</p>
      ) : (
        <InflowBody
          data={data}
          mode={mode}
          hidden={hidden}
          onToggle={(name) =>
            setHidden(() => {
              const next = new Set(hidden);
              if (next.has(name)) next.delete(name);
              else next.add(name);
              return next;
            })
          }
        />
      )}
    </Card>
  );
}

function InflowBody({
  data,
  mode,
  hidden,
  onToggle,
}: {
  data: CompanyInflow;
  mode: Mode;
  hidden: Set<string>;
  onToggle: (name: string) => void;
}) {
  const view = useMemo(() => {
    const today = data.today;
    const byDay = index(data.days);
    const byMonth = index(data.months);

    const color = new Map<string, string>();
    let i = 0;
    for (const s of data.sources) {
      color.set(
        s.name,
        s.is_manual ? CHART_AXIS_LINE_COLOR : BRAND_CHART_COLORS[i++ % (BRAND_CHART_COLORS.length - 1)],
      );
    }

    const days = Array.from({ length: DAY_WINDOW }, (_, k) => addDays(today, k - DAY_WINDOW + 1));
    const prevDays = days.map((k) => addDays(k, -DAY_WINDOW));
    const months = Array.from({ length: MONTH_WINDOW }, (_, k) => monthKey(today, MONTH_WINDOW - 1 - k));

    // Month-to-date vs the same days of the previous month (both inside the 62-day window).
    const dom = Number(today.slice(8, 10));
    const thisMonthDays = Array.from({ length: dom }, (_, k) => addDays(monthKey(today), k));
    const prevMonthStart = monthKey(today, 1);
    const prevMonthDays = Array.from({ length: dom }, (_, k) => addDays(prevMonthStart, k)).filter(
      (k) => monthKey(k) === prevMonthStart,
    );

    return { today, byDay, byMonth, color, days, prevDays, months, thisMonthDays, prevMonthDays };
  }, [data]);

  const visible = data.sources.filter((s) => !hidden.has(s.name));
  const sumVisible = (byBucket: Map<string, Map<string, number>>, keys: string[]) =>
    visible.reduce((acc, s) => acc + sumRange(byBucket.get(s.name), keys), 0);

  const todayN = sumVisible(view.byDay, [view.today]);
  const yesterdayN = sumVisible(view.byDay, [addDays(view.today, -1)]);
  const monthN = sumVisible(view.byDay, view.thisMonthDays);
  const prevMonthN = sumVisible(view.byDay, view.prevMonthDays);
  const d30 = sumVisible(view.byDay, view.days);
  const prev30 = sumVisible(view.byDay, view.prevDays);

  const keys = mode === "day" ? view.days : view.months;
  const byBucket = mode === "day" ? view.byDay : view.byMonth;
  const rows = keys.map((k) => {
    const row: Record<string, string | number> = { label: mode === "day" ? dayLabel(k) : monthLabel(k) };
    for (const s of visible) row[s.name] = byBucket.get(s.name)?.get(k) ?? 0;
    return row;
  });

  const thisMonthKey = monthKey(view.today);
  const prevMonthKey = monthKey(view.today, 1);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Stat label="Сегодня" value={todayN} note={`вчера ${yesterdayN}`} />
        <Stat
          label="Этот месяц"
          value={monthN}
          note={`прошлый за те же дни — ${prevMonthN}`}
          delta={pct(monthN, prevMonthN)}
        />
        <Stat label="За 30 дней" value={d30} note={`предыдущие 30 — ${prev30}`} delta={pct(d30, prev30)} />
      </div>

      <div>
        <div className="flex flex-wrap gap-2 mb-3" aria-label="Источники — нажмите, чтобы скрыть или показать">
          {data.sources.map((s) => {
            const off = hidden.has(s.name);
            return (
              <button
                key={s.name}
                type="button"
                aria-pressed={!off}
                onClick={() => onToggle(s.name)}
                className={`inline-flex items-center gap-1.5 h-7 px-3 rounded-full border type-caption transition-colors ${C.focusRing} ${
                  off
                    ? "border-dashed border-brand-border text-brand-muted line-through"
                    : "border-brand-border bg-white text-brand-primary hover:bg-brand-bg"
                }`}
              >
                <span className="size-2.5 rounded-sm shrink-0" style={{ background: view.color.get(s.name) }} />
                {s.name}
              </button>
            );
          })}
        </div>
        <ChartContainer
          height={240}
          aria-label={mode === "day" ? "Новые заявки по дням за 30 дней" : "Новые заявки по месяцам за год"}
        >
          <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: CHART_AXIS_COLOR }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
              minTickGap={12}
            />
            <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: CHART_AXIS_COLOR }} axisLine={false} tickLine={false} width={32} />
            <ChartTooltip />
            {visible.map((s) => (
              <Bar key={s.name} dataKey={s.name} name={s.name} stackId="s" fill={view.color.get(s.name)} isAnimationActive={false} />
            ))}
          </BarChart>
        </ChartContainer>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[28rem]">
          <thead>
            <tr className="type-table-header text-brand-muted">
              <th className="text-left font-semibold pb-2">Источник</th>
              {mode === "day" ? (
                <>
                  <th className="text-right font-semibold pb-2">30 дней</th>
                  <th className="text-right font-semibold pb-2">Предыдущие 30</th>
                </>
              ) : (
                <>
                  <th className="text-right font-semibold pb-2">Этот месяц</th>
                  <th className="text-right font-semibold pb-2">Прошлый</th>
                </>
              )}
              <th className="text-right font-semibold pb-2">За год</th>
            </tr>
          </thead>
          <tbody>
            {data.sources.map((s) => {
              const cur =
                mode === "day"
                  ? sumRange(view.byDay.get(s.name), view.days)
                  : sumRange(view.byMonth.get(s.name), [thisMonthKey]);
              const prev =
                mode === "day"
                  ? sumRange(view.byDay.get(s.name), view.prevDays)
                  : sumRange(view.byMonth.get(s.name), [prevMonthKey]);
              const off = hidden.has(s.name);
              return (
                <tr key={s.name} className={`border-t border-brand-border ${off ? "text-brand-muted" : "text-brand-primary"}`}>
                  <td className="py-2.5 pr-3">
                    <span className="inline-flex items-center gap-2 type-body">
                      <span className="size-2.5 rounded-sm shrink-0" style={{ background: view.color.get(s.name) }} />
                      {s.name}
                    </span>
                  </td>
                  <td className="py-2.5 text-right type-body tabular-nums font-semibold">{cur}</td>
                  <td className="py-2.5 text-right type-body tabular-nums text-brand-muted">
                    {prev}
                    <Trend cur={cur} prev={prev} />
                  </td>
                  <td className="py-2.5 text-right type-body tabular-nums text-brand-muted">{s.total}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="type-hint text-brand-muted mt-3">
          Считаются все новые лиды. «Вручную и загрузка базы» — лиды без источника и без формы сайта;
          загрузка базы даёт всплеск в один день, поэтому по умолчанию эта строка скрыта —
          включите её кнопкой выше, цифры сверху пересчитаются.
        </p>
      </div>
    </div>
  );
}

function Stat({ label, value, note, delta }: { label: string; value: number; note: string; delta?: number | null }) {
  return (
    <div className="rounded-lg bg-brand-bg p-4">
      <span className="type-caption text-brand-muted">{label}</span>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="type-kpi-number text-brand-primary">{value}</span>
        <span className="type-label text-brand-muted">{plural(value, "заявка", "заявки", "заявок")}</span>
        {delta != null && delta !== 0 && (
          <span className={`inline-flex items-center type-label tabular-nums ${delta > 0 ? "text-success" : "text-rose"}`}>
            {delta > 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {delta > 0 ? "+" : ""}
            {delta}%
          </span>
        )}
      </div>
      <span className="type-hint not-italic text-brand-muted">{note}</span>
    </div>
  );
}

function Trend({ cur, prev }: { cur: number; prev: number }) {
  if (cur === prev) return null;
  return (
    <span className={`inline-flex align-middle ml-1 ${cur > prev ? "text-success" : "text-rose"}`} aria-label={cur > prev ? "рост" : "спад"}>
      {cur > prev ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
    </span>
  );
}
