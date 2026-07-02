"use client";

// CEO overview — the role-gated /today variant (Sprint CEO G5, redesigned).
// «Триаж-обзор»: hero verdict → KPI band with week-over-week deltas → action
// zone (stuck + manager load) → sources with trend → collapsible daily chart.
// Deals are rare/slow so this is about INCOMING LEAD FLOW, never revenue.
// Built entirely on the existing brand tokens / Card / recharts wrappers.

import { useMemo } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  Megaphone,
  Eye,
  ChevronRight,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  LineChart,
  Line,
  ResponsiveContainer,
} from "recharts";

import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { ChartContainer, ChartTooltip, BRAND_CHART_COLORS } from "@/components/ui/Chart";
import { useCompanySummary, useCompanyAttention } from "@/lib/hooks/use-company";
import type { CompanySummary, StuckLead, ManagerLoad } from "@/lib/types";

const SOURCE_COLORS = ["#FF4E00", "#2a78d6", "#1baf7a", "#eda100", "#9085e9", "#6B6B6B"];
const STUCK_PREVIEW = 5;

function fmtDay(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** WoW percent; null when there's no prior baseline to compare against. */
function wowPct(cur: number, prior: number): number | null {
  if (prior <= 0) return cur > 0 ? null : 0;
  return Math.round(((cur - prior) / prior) * 100);
}

// ── daily series pivot for the collapsible chart ────────────────────
function useDailySeries(summary: CompanySummary | undefined) {
  return useMemo(() => {
    if (!summary) return { rows: [], series: [] as { key: string; name: string; color: string }[] };
    const order = summary.sources.map((s) => s.source_id ?? "none");
    const nameOf = new Map(summary.sources.map((s) => [s.source_id ?? "none", s.name]));
    const series = order.map((key, i) => ({
      key,
      name: nameOf.get(key) ?? "—",
      color: SOURCE_COLORS[i % SOURCE_COLORS.length],
    }));
    const byDay = new Map<string, Record<string, number | string>>();
    for (const p of summary.daily) {
      const label = fmtDay(p.date);
      const row = byDay.get(label) ?? { label };
      const key = p.source_id ?? "none";
      row[key] = ((row[key] as number) ?? 0) + p.count;
      byDay.set(label, row);
    }
    return { rows: Array.from(byDay.values()), series };
  }, [summary]);
}

// daily totals (all sources) → tiny sparkline series
function useDailyTotals(summary: CompanySummary | undefined): number[] {
  return useMemo(() => {
    if (!summary) return [];
    const byDay = new Map<string, number>();
    for (const p of summary.daily) byDay.set(p.date, (byDay.get(p.date) ?? 0) + p.count);
    return Array.from(byDay.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([, v]) => v);
  }, [summary]);
}

export function CeoOverview() {
  // Trailing week + 14-day trend across the whole screen — one consistent
  // window, no period toggle (a month/week switch only re-scoped part of the
  // screen, which read as dishonest). Month view, if wanted, is a separate
  // properly-scoped feature.
  const { data: summary, isLoading, isError: summaryError } = useCompanySummary();
  const { data: attention, isError: attentionError } = useCompanyAttention();
  const { rows, series } = useDailySeries(summary);
  const totals = useDailyTotals(summary);
  const failed = summaryError || attentionError;

  return (
    <div className={pageContainerVariants({ surface: "reading" })}>
      <PageHeader icon={<Eye size={20} />} title="Обзор" />

      {failed ? (
        <div className="rounded-card border border-rose/20 bg-rose/5 p-6 mt-2">
          <p className="type-card-title text-rose">Не удалось загрузить сводку</p>
          <p className="type-body text-brand-muted mt-1">Обновите страницу — данные временно недоступны.</p>
        </div>
      ) : (
        <div className="space-y-6 mt-2">
          <HeroVerdict summary={summary} attention={attention} loading={isLoading} />

          <KpiBand summary={summary} oldestIdle={attention?.oldest_days_idle ?? 0} totals={totals} />

          <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr] gap-4">
            <StuckList stuck={attention?.stuck} loading={!attention} />
            <ManagerLoadCard managers={attention?.managers} loading={!attention} />
          </div>

          <SourcesCard summary={summary} loading={isLoading} />

          <DailyDisclosure rows={rows} series={series} hasData={(summary?.daily.length ?? 0) > 0} />
        </div>
      )}
    </div>
  );
}

// ── hero verdict ────────────────────────────────────────────────────
function HeroVerdict({
  summary,
  attention,
  loading,
}: {
  summary: CompanySummary | undefined;
  attention: { stuck: StuckLead[]; managers: ManagerLoad[]; oldest_days_idle: number } | undefined;
  loading: boolean;
}) {
  if (!summary) {
    return (
      <Card>
        <p className="type-body text-brand-muted">{loading ? "Загрузка…" : "Нет данных"}</p>
      </Card>
    );
  }

  const pct = wowPct(summary.leads_7d, summary.leads_7d_prior);
  const stuck = summary.stuck_count;
  const oldest = attention?.oldest_days_idle ?? 0;
  const overloaded = (attention?.managers ?? []).some(
    (m) => m.max_active_deals && m.in_work / m.max_active_deals > 0.85,
  );

  const tone: "success" | "warning" | "rose" =
    (pct != null && pct <= -25) || oldest >= 14 || overloaded
      ? "rose"
      : (pct != null && pct < 0) || (stuck > 0 && oldest >= 7)
        ? "warning"
        : "success";
  const dot = { success: "bg-success", warning: "bg-warning", rose: "bg-rose" }[tone];

  let headline: string;
  if (pct == null) {
    headline =
      summary.leads_7d > 0
        ? `Поток заявок пошёл — ${summary.leads_7d} за неделю`
        : "Заявок за неделю пока нет";
  } else if (pct >= 0) {
    headline = `Поток заявок в норме — на этой неделе на ${pct}% больше, чем на прошлой`;
  } else {
    headline = `Поток заявок снижается — на ${Math.abs(pct)}% меньше, чем на прошлой неделе`;
  }

  const subtitle =
    stuck > 0
      ? `Требует внимания: ${stuck} ${plural(stuck, "заявка", "заявки", "заявок")} без движения, самой старой ${oldest} ${plural(oldest, "день", "дня", "дней")}`
      : "Всё под контролем — зависших заявок нет";

  return (
    <Card className="flex items-start gap-3.5">
      <span className={`mt-1.5 size-2.5 shrink-0 rounded-full ${dot}`} aria-hidden />
      <div className="min-w-0">
        <p className="type-card-title text-brand-primary">{headline}</p>
        <p className="type-body text-brand-muted mt-1">{subtitle}</p>
      </div>
    </Card>
  );
}

// ── KPI band ────────────────────────────────────────────────────────
function KpiBand({
  summary,
  oldestIdle,
  totals,
}: {
  summary: CompanySummary | undefined;
  oldestIdle: number;
  totals: number[];
}) {
  const pct = summary ? wowPct(summary.leads_7d, summary.leads_7d_prior) : null;
  const conv = summary?.ad_conversion_pct;
  const convPrior = summary?.ad_conversion_pct_prior;
  const convDelta = conv != null && convPrior != null ? Math.round((conv - convPrior) * 10) / 10 : null;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KpiTile
        label="Заявок за неделю"
        value={summary ? String(summary.leads_7d) : "—"}
        delta={pct != null ? { pct, good: pct >= 0, unit: "%", suffix: " к прошлой неделе" } : null}
        sparkline={totals}
      />
      <KpiTile
        label="В среднем в день"
        value={summary ? String(summary.avg_per_day_7d) : "—"}
        note="за последние 7 дней"
      />
      <KpiTile
        label="Конверсия с рекламы"
        value={conv != null ? `${conv}%` : "—"}
        note="заявка → квалификация"
        delta={convDelta != null && convDelta !== 0 ? { pct: convDelta, good: convDelta >= 0, unit: " п.п.", suffix: "" } : null}
      />
      <KpiTile
        label="Без движения"
        value={summary ? String(summary.stuck_count) : "—"}
        note={summary && summary.stuck_count > 0 ? `самой старой ${oldestIdle} ${plural(oldestIdle, "день", "дня", "дней")}` : "всё в движении"}
        danger={!!summary && summary.stuck_count > 0}
      />
    </div>
  );
}

function KpiTile({
  label,
  value,
  note,
  delta,
  sparkline,
  danger,
}: {
  label: string;
  value: string;
  note?: string;
  delta?: { pct: number; good: boolean; unit: string; suffix: string } | null;
  sparkline?: number[];
  danger?: boolean;
}) {
  const wrap = danger ? "bg-rose/5 border-rose/15" : "bg-white border-brand-border";
  const valueColor = danger ? "text-rose" : "text-brand-primary";
  return (
    <div className={`rounded-card border ${wrap} p-4 flex flex-col gap-1.5`}>
      <span className={`type-caption ${danger ? "text-rose" : "text-brand-muted"}`}>{label}</span>
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className={`type-kpi-number tabular-nums ${valueColor}`}>{value}</span>
        {delta && (
          <span className={`inline-flex items-center gap-0.5 type-label ${delta.good ? "text-success" : "text-rose"}`}>
            {delta.pct >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {delta.pct >= 0 ? "+" : ""}
            <span className="tabular-nums">{delta.pct}</span>
            {delta.unit}
          </span>
        )}
      </div>
      {note && <span className={`type-hint not-italic ${danger ? "text-rose/80" : "text-brand-muted"}`}>{note}</span>}
      {sparkline && sparkline.length > 1 && (
        <div className="h-5 w-full mt-0.5 hidden sm:block">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkline.map((v, i) => ({ i, v }))} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
              <Line type="monotone" dataKey="v" stroke={BRAND_CHART_COLORS[0]} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// ── action zone: stuck leads ────────────────────────────────────────
function StuckList({ stuck, loading }: { stuck: StuckLead[] | undefined; loading: boolean }) {
  const items = stuck ?? [];
  const preview = items.slice(0, STUCK_PREVIEW);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Требует внимания</CardTitle>
        {items.length > 0 && <Badge variant="rose">{items.length}</Badge>}
      </CardHeader>
      {preview.length > 0 ? (
        <ul className="space-y-1.5">
          {preview.map((s) => (
            <li key={s.lead_id}>
              <Link
                href={`/leads/${s.lead_id}`}
                className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-card bg-brand-bg hover:bg-brand-border/50 transition-colors active:scale-[0.99]"
              >
                <span className="min-w-0">
                  <span className="type-body text-brand-primary block truncate">{s.company_name}</span>
                  <span className="type-hint text-brand-muted block truncate not-italic">
                    {[s.source_name ?? "Без источника", s.manager_name, s.stage_name && `этап «${s.stage_name}»`]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                <IdleChip days={s.days_idle} />
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="type-body text-brand-muted text-center py-6">
          {loading ? "Загрузка…" : "Всё в движении — зависших заявок нет"}
        </p>
      )}
      {items.length > STUCK_PREVIEW && (
        <p className="type-hint not-italic text-brand-muted mt-2 px-1">и ещё {items.length - STUCK_PREVIEW}</p>
      )}
    </Card>
  );
}

function IdleChip({ days }: { days: number }) {
  const cls = days >= 14 ? "bg-rose/10 text-rose" : "bg-warning/10 text-warning";
  return (
    <span className={`shrink-0 inline-flex items-center gap-1 type-label rounded-full px-2.5 py-1 ${cls}`}>
      <Clock size={12} />
      <span className="tabular-nums">{days}</span> дн.
    </span>
  );
}

// ── action zone: manager load ───────────────────────────────────────
function ManagerLoadCard({ managers, loading }: { managers: ManagerLoad[] | undefined; loading: boolean }) {
  const rows = useMemo(() => {
    const list = (managers ?? []).map((m) => {
      const cap = m.max_active_deals && m.max_active_deals > 0 ? m.max_active_deals : null;
      // load = null when capacity is unknown — render a neutral grey bar rather
      // than fabricating an "overload" zone (the previous 0.9 mislabelled a
      // stuck lead as capacity overload).
      const load = cap ? m.in_work / cap : null;
      return { ...m, load };
    });
    const maxIn = Math.max(1, ...list.map((m) => m.in_work));
    const withBar = list.map((m) => {
      const zone =
        m.load == null ? "bg-brand-muted" : m.load > 0.85 ? "bg-rose" : m.load > 0.6 ? "bg-warning" : "bg-success";
      const width =
        m.load == null ? Math.round((m.in_work / maxIn) * 100) : Math.min(100, Math.round(m.load * 100));
      return { ...m, zone, width };
    });
    return withBar.sort(
      (a, b) => (b.load ?? -1) - (a.load ?? -1) || b.stuck - a.stuck || b.in_work - a.in_work,
    );
  }, [managers]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Нагрузка менеджеров</CardTitle>
      </CardHeader>
      {rows.length > 0 ? (
        <>
          <ul className="space-y-2.5">
            {rows.map((m) => (
              <li key={m.user_id}>
                <Link
                  href={`/team/${m.user_id}` as `/team/${string}`}
                  className="block px-3 py-2 rounded-card hover:bg-brand-bg transition-colors active:scale-[0.99]"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="type-body text-brand-primary truncate">{m.name}</span>
                    <span className="type-hint text-brand-muted shrink-0 not-italic">
                      в работе <span className="tabular-nums text-brand-primary">{m.in_work}</span>
                      {m.stuck > 0 && (
                        <>
                          {" · "}
                          <span className="tabular-nums text-rose">{m.stuck}</span> стоп
                        </>
                      )}
                    </span>
                  </div>
                  <span className="mt-1.5 block h-2 rounded-full bg-brand-bg overflow-hidden">
                    <span className={`block h-full rounded-full ${m.zone}`} style={{ width: `${m.width}%` }} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-3 mt-3 px-1 type-hint text-brand-muted not-italic">
            <LegendDot cls="bg-rose" label="перегруз" />
            <LegendDot cls="bg-warning" label="норма" />
            <LegendDot cls="bg-success" label="есть запас" />
          </div>
        </>
      ) : (
        <p className="type-body text-brand-muted text-center py-6">
          {loading ? "Загрузка…" : "Нет заявок в работе"}
        </p>
      )}
    </Card>
  );
}

function LegendDot({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`size-2 rounded-full ${cls}`} />
      {label}
    </span>
  );
}

// ── sources ─────────────────────────────────────────────────────────
function SourcesCard({ summary, loading }: { summary: CompanySummary | undefined; loading: boolean }) {
  const sources = summary?.sources ?? [];
  const maxLeads = Math.max(1, ...sources.map((s) => s.leads));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Откуда пришли</CardTitle>
        <span className="type-hint not-italic text-brand-muted">ранжировано по объёму</span>
      </CardHeader>
      {sources.length > 0 ? (
        <div className="space-y-2">
          {sources.map((s) => {
            const delta = s.leads - s.prev_leads;
            return (
              <div key={s.source_id ?? "none"} className="grid grid-cols-[6.5rem_1fr_auto] sm:grid-cols-[8.5rem_1fr_auto] items-center gap-2 sm:gap-3">
                <span className="type-body text-brand-primary inline-flex items-center gap-1.5 truncate">
                  <Megaphone size={14} className={s.is_paid ? "text-brand-accent" : "text-brand-muted"} />
                  {s.name}
                </span>
                <span className="h-2 rounded-full bg-brand-bg overflow-hidden">
                  <span
                    className={`block h-full rounded-full ${s.is_paid ? "bg-brand-accent" : "bg-brand-muted"}`}
                    style={{ width: `${Math.round((s.leads / maxLeads) * 100)}%` }}
                  />
                </span>
                <span className="type-hint text-brand-muted text-right whitespace-nowrap not-italic">
                  <span className="tabular-nums font-medium text-brand-primary">{s.leads}</span>
                  {" · "}
                  <span className="tabular-nums">{s.conversion_pct}%</span>
                  {delta !== 0 && (
                    <span className={`inline-flex items-center align-middle ml-1 ${delta > 0 ? "text-success" : "text-rose"}`}>
                      {delta > 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
                    </span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="type-body text-brand-muted text-center py-6">
          {loading ? "Загрузка…" : "Нет данных по источникам"}
        </p>
      )}
    </Card>
  );
}

// ── collapsible daily chart ─────────────────────────────────────────
function DailyDisclosure({
  rows,
  series,
  hasData,
}: {
  rows: Record<string, number | string>[];
  series: { key: string; name: string; color: string }[];
  hasData: boolean;
}) {
  return (
    <details className="group rounded-card border border-brand-border bg-white overflow-hidden">
      <summary className="flex items-center justify-between gap-2 px-5 sm:px-6 py-4 cursor-pointer list-none [&::-webkit-details-marker]:hidden">
        <span className="type-card-title text-brand-primary">Заявки по дням</span>
        <span className="flex items-center gap-2 type-hint text-brand-muted not-italic">
          последние 14 дней
          <ChevronRight size={16} className="transition-transform duration-200 group-open:rotate-90" />
        </span>
      </summary>
      <div className="px-5 sm:px-6 pb-5">
        {hasData ? (
          <>
            <div className="flex flex-wrap gap-3 mb-2">
              {series.map((s) => (
                <span key={s.key} className="inline-flex items-center gap-1.5 type-hint text-brand-muted not-italic">
                  <span className="size-2.5 rounded-sm" style={{ background: s.color }} />
                  {s.name}
                </span>
              ))}
            </div>
            <ChartContainer height={220} aria-label="Входящие заявки по дням с разбивкой по источникам">
              <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E3DC" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                <ChartTooltip />
                {series.map((s) => (
                  <Bar key={s.key} dataKey={s.key} name={s.name} stackId="s" fill={s.color} radius={[2, 2, 0, 0]} />
                ))}
              </BarChart>
            </ChartContainer>
          </>
        ) : (
          <p className="type-body text-brand-muted text-center py-6">Пока нет заявок за период</p>
        )}
      </div>
    </details>
  );
}

// ── ru pluralization ────────────────────────────────────────────────
function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}
