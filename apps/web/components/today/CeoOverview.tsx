"use client";

// CEO overview — the role-gated /today variant (Sprint CEO G5). Focused on
// incoming-lead FLOW (deals are rare/slow, so revenue stays out): how many
// leads, from where, ad conversion, by day, who's working them, what's stuck.

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ArrowDownRight, Clock, Megaphone, Eye } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid } from "recharts";

import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { ChartContainer, ChartTooltip } from "@/components/ui/Chart";
import { useCompanySummary, useCompanyAttention } from "@/lib/hooks/use-company";
import type { CompanySummary } from "@/lib/types";

const SOURCE_COLORS = ["#FF4E00", "#2a78d6", "#1baf7a", "#eda100", "#9085e9", "#6B6B6B"];

function fmtDay(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Pivot the flat daily[] into recharts rows + ordered source series. */
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

export function CeoOverview() {
  const [period, setPeriod] = useState<"week" | "month">("week");
  const { data: summary, isLoading } = useCompanySummary(period);
  const { data: attention } = useCompanyAttention();
  const { rows, series } = useDailySeries(summary);

  const todayDelta = summary ? summary.leads_today - summary.leads_yesterday : 0;
  const maxSourceLeads = Math.max(1, ...(summary?.sources.map((s) => s.leads) ?? [1]));

  return (
    <div className={pageContainerVariants({ surface: "reading" })}>
      <div className="flex items-center justify-between flex-wrap gap-2">
        <PageHeader icon={<Eye size={20} />} title="Обзор" />
        <div className="inline-flex rounded-full border border-brand-border bg-white p-0.5">
          {(["week", "month"] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              className={`px-3 py-1 type-caption font-semibold rounded-full transition ${
                period === p ? "bg-brand-soft text-brand-accent" : "text-brand-muted hover:text-brand-primary"
              }`}
            >
              {p === "week" ? "Неделя" : "Месяц"}
            </button>
          ))}
        </div>
      </div>

      {/* Pulse */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard label="Заявок сегодня" value={summary?.leads_today ?? "—"}>
          {summary && (
            <span className={`type-caption inline-flex items-center gap-0.5 ${todayDelta >= 0 ? "text-success" : "text-rose"}`}>
              {todayDelta >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
              {todayDelta >= 0 ? "+" : ""}{todayDelta} ко вчера
            </span>
          )}
        </MetricCard>
        <MetricCard label="За 7 дней" value={summary?.leads_7d ?? "—"}>
          <span className="type-caption text-brand-muted">{summary?.avg_per_day_7d ?? 0} в день</span>
        </MetricCard>
        <MetricCard
          label="Конверсия с рекламы"
          value={summary?.ad_conversion_pct != null ? `${summary.ad_conversion_pct}%` : "—"}
        >
          <span className="type-caption text-brand-muted">заявка → квалификация</span>
        </MetricCard>
        <MetricCard label="Без движения" value={summary?.stuck_count ?? "—"} danger>
          <span className="type-caption text-rose">7+ дней без касания</span>
        </MetricCard>
      </div>

      {/* Leads by day */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-base font-bold text-brand-primary">Заявки по дням</h2>
          <span className="type-caption text-brand-muted">последние 14 дней</span>
        </div>
        <div className="flex flex-wrap gap-3 mb-2">
          {series.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1.5 type-caption text-brand-muted">
              <span className="w-2.5 h-2.5 rounded-sm" style={{ background: s.color }} />
              {s.name}
            </span>
          ))}
        </div>
        {rows.length > 0 ? (
          <ChartContainer height={220} aria-label="Входящие заявки по дням с разбивкой по источникам">
            <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 8, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E3DC" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
              <ChartTooltip />
              {series.map((s) => (
                <Bar key={s.key} dataKey={s.key} name={s.name} stackId="s" fill={s.color} radius={[2, 2, 0, 0]} />
              ))}
            </BarChart>
          </ChartContainer>
        ) : (
          <EmptyHint loading={isLoading} text="Пока нет заявок за период." />
        )}
      </section>

      {/* Sources */}
      <section>
        <h2 className="text-base font-bold text-brand-primary mb-2">Откуда пришли</h2>
        <div className="space-y-1.5">
          {summary?.sources.map((s) => (
            <div key={s.source_id ?? "none"} className="grid grid-cols-[9rem_1fr_5.5rem] items-center gap-3">
              <span className="type-caption text-brand-primary inline-flex items-center gap-1.5 truncate">
                <Megaphone size={13} className={s.is_paid ? "text-brand-accent" : "text-brand-muted"} />
                {s.name}
              </span>
              <span className="h-2 rounded-full bg-brand-bg overflow-hidden">
                <span
                  className="block h-full rounded-full bg-brand-accent"
                  style={{ width: `${Math.round((s.leads / maxSourceLeads) * 100)}%` }}
                />
              </span>
              <span className="type-caption text-brand-muted text-right">
                <span className="font-semibold text-brand-primary">{s.leads}</span> · {s.conversion_pct}%
              </span>
            </div>
          ))}
          {!summary?.sources.length && <EmptyHint loading={isLoading} text="Нет данных по источникам." />}
        </div>
      </section>

      {/* Managers */}
      <section>
        <h2 className="text-base font-bold text-brand-primary mb-2">Заявки в работе по менеджерам</h2>
        <div className="rounded-card border border-brand-border bg-white overflow-hidden">
          <div className="grid grid-cols-[1fr_4rem_5rem_4rem] gap-2 px-4 py-2 type-caption text-brand-muted border-b border-brand-border">
            <span>Менеджер</span>
            <span className="text-right">в работе</span>
            <span className="text-right">за неделю</span>
            <span className="text-right">без движ.</span>
          </div>
          {attention?.managers.map((m) => (
            <Link
              key={m.user_id}
              href={`/team/${m.user_id}` as `/team/${string}`}
              className="grid grid-cols-[1fr_4rem_5rem_4rem] gap-2 px-4 py-2.5 items-center border-b border-brand-border last:border-0 hover:bg-brand-bg transition-colors"
            >
              <span className="type-body text-brand-primary truncate">{m.name}</span>
              <span className="type-body text-right font-semibold text-brand-primary">{m.in_work}</span>
              <span className="type-body text-right text-brand-muted">+{m.new_week}</span>
              <span className={`type-body text-right font-semibold ${m.stuck > 0 ? "text-rose" : "text-brand-muted"}`}>
                {m.stuck > 0 ? m.stuck : "—"}
              </span>
            </Link>
          ))}
          {!attention?.managers.length && <EmptyHint loading={!attention} text="Нет заявок в работе." />}
        </div>
      </section>

      {/* Stuck */}
      <section>
        <h2 className="text-base font-bold text-brand-primary mb-2 inline-flex items-center gap-2">
          Без движения
          {attention?.stuck.length ? (
            <span className="type-caption text-rose bg-rose/10 rounded-full px-2 py-0.5">{attention.stuck.length}</span>
          ) : null}
        </h2>
        <div className="rounded-card border border-brand-border bg-white overflow-hidden">
          {attention?.stuck.map((s) => (
            <Link
              key={s.lead_id}
              href={`/leads/${s.lead_id}`}
              className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-brand-border last:border-0 hover:bg-brand-bg transition-colors"
            >
              <span className="min-w-0">
                <span className="type-body text-brand-primary block truncate">{s.company_name}</span>
                <span className="type-caption text-brand-muted block truncate">
                  {(s.source_name ?? "Без источника")}{s.manager_name ? ` · ${s.manager_name}` : ""}
                </span>
              </span>
              <span className="shrink-0 type-caption text-rose bg-rose/10 rounded-full px-2 py-1 inline-flex items-center gap-1">
                <Clock size={12} /> {s.days_idle} дн.
              </span>
            </Link>
          ))}
          {!attention?.stuck.length && <EmptyHint loading={!attention} text="Всё в движении — зависших заявок нет." />}
        </div>
      </section>
    </div>
  );
}

function MetricCard({
  label,
  value,
  danger,
  children,
}: {
  label: string;
  value: string | number;
  danger?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className={`rounded-card border p-4 ${danger ? "border-rose/30 bg-rose/5" : "border-brand-border bg-white"}`}>
      <div className={`type-caption ${danger ? "text-rose" : "text-brand-muted"}`}>{label}</div>
      <div className={`text-2xl font-bold leading-tight ${danger ? "text-rose" : "text-brand-primary"}`}>{value}</div>
      {children}
    </div>
  );
}

function EmptyHint({ loading, text }: { loading: boolean; text: string }) {
  return (
    <p className="type-caption text-brand-muted px-4 py-6 text-center">
      {loading ? "Загрузка…" : text}
    </p>
  );
}
