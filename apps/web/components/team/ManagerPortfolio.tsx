"use client";

import Link from "next/link";
import { Loader2, AlertTriangle, Wallet, Package, Sparkles, ArrowUpRight } from "lucide-react";
import { useManagerPortfolio } from "@/lib/hooks/use-manager-portfolio";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/Empty";

function fmtSum(n: number): string {
  if (!n) return "—";
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(0)} тыс ₽`;
  return `${Math.round(n)} ₽`;
}

function fmtNum(n: number): string {
  return new Intl.NumberFormat("ru-RU").format(n);
}

// Friendly RU labels for the known DrinkX segments; unknown values pass through.
const SEGMENT_LABEL: Record<string, string> = {
  retail: "Ритейл",
  horeca: "HoReCa",
  qsr: "QSR",
  azs: "АЗС",
  gas: "АЗС",
  foodmarket: "Фудмаркеты",
  foodmarkets: "Фудмаркеты",
};

function segLabel(s: string): string {
  return SEGMENT_LABEL[s.toLowerCase()] ?? s;
}

export function ManagerPortfolio({ userId }: { userId: string | null }) {
  const { data: p, isLoading, isError } = useManagerPortfolio(userId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 size={20} className="animate-spin text-brand-muted" />
      </div>
    );
  }
  if (isError || !p) {
    return (
      <Card>
        <div className="flex items-start gap-2 bg-rose/5 border border-rose/20 rounded-xl px-3 py-2">
          <AlertTriangle size={14} className="text-rose shrink-0 mt-0.5" />
          <p className="type-caption text-rose">Не удалось загрузить портфель.</p>
        </div>
      </Card>
    );
  }

  if (p.kpi.active_count === 0) {
    return (
      <Card>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"><Wallet /></EmptyMedia>
            <EmptyTitle>Нет активных сделок</EmptyTitle>
            <EmptyDescription>
              У этого менеджера сейчас нет сделок в работе. Как только появятся —
              здесь будет разбивка по сегментам, этапам и потенциалу.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </Card>
    );
  }

  const maxSegAmount = Math.max(1, ...p.by_segment.map((s) => s.amount));

  return (
    <div className="flex flex-col gap-6">
      {/* KPI tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <Kpi icon={<Wallet size={16} />} label="Активных сделок" value={fmtNum(p.kpi.active_count)} note={`потенциал ${fmtSum(p.kpi.total_amount)}`} />
        <Kpi icon={<Package size={16} />} label="Потенциал, штук" value={fmtNum(p.kpi.total_quantity)} note={p.kpi.avg_amount ? `средний чек ${fmtSum(p.kpi.avg_amount)}` : "—"} />
        <Kpi icon={<Sparkles size={16} className="text-success" />} label="Новых за неделю" value={fmtNum(p.kpi.new_7d)} note={`${fmtNum(p.kpi.new_30d)} за месяц`} accent />
        <Kpi icon={<AlertTriangle size={16} className="text-rose" />} label="Под угрозой" value={fmtNum(p.kpi.at_risk_count)} note={fmtSum(p.kpi.at_risk_amount)} danger />
      </div>

      {/* By segment */}
      <Card>
        <CardHeader><CardTitle>По сегментам</CardTitle></CardHeader>
        <div className="flex items-center gap-3 mb-2 type-hint text-brand-muted uppercase tracking-wider">
          <span className="w-28 shrink-0">Сегмент</span>
          <span className="flex-1" />
          <span className="w-12 shrink-0 text-right">Сделок</span>
          <span className="w-24 shrink-0 text-right">Сумма</span>
        </div>
        <ul className="flex flex-col gap-2.5">
          {p.by_segment.map((s) => (
            <li key={s.segment} className="flex items-center gap-3">
              <span className="w-28 shrink-0 type-body text-brand-primary truncate">{segLabel(s.segment)}</span>
              <div className="flex-1 h-2 rounded-full bg-brand-bg overflow-hidden">
                <div
                  className="h-full rounded-full bg-brand-accent"
                  style={{ width: `${Math.round((s.amount / maxSegAmount) * 100)}%` }}
                />
              </div>
              <span className="w-12 shrink-0 text-right type-body text-brand-primary tabular-nums">{s.count}</span>
              <span className="w-24 shrink-0 text-right type-body text-brand-primary font-semibold tabular-nums whitespace-nowrap">{fmtSum(s.amount)}</span>
            </li>
          ))}
        </ul>
      </Card>

      {/* By stage + by priority side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle>По этапам</CardTitle></CardHeader>
          <MiniTable
            firstCol="Этап"
            rows={p.by_stage.map((s) => ({
              key: s.stage_id,
              label: s.stage_name,
              count: s.count,
              amount: s.amount,
              // Drill into the manager's deals on that exact stage.
              href: userId ? `/pipeline?assigned_to=${userId}&stage=${s.stage_id}` : undefined,
            }))}
          />
        </Card>
        <Card>
          <CardHeader><CardTitle>По приоритету</CardTitle></CardHeader>
          <MiniTable firstCol="Приоритет" rows={p.by_priority.map((s) => ({ key: s.priority, label: s.label, count: s.count, amount: s.amount }))} />
        </Card>
      </div>

      {/* Top deals */}
      <Card>
        <CardHeader><CardTitle>Топ сделок по сумме</CardTitle></CardHeader>
        <ul className="flex flex-col gap-1.5">
          {p.top_deals.map((d) => (
            <li key={d.lead_id}>
              <Link
                href={`/leads/${d.lead_id}`}
                className="flex items-center gap-3 px-3 py-2.5 rounded-card bg-brand-bg hover:bg-brand-bg/70 transition-colors group"
              >
                <div className="flex-1 min-w-0">
                  <p className="type-body text-brand-primary truncate">{d.company_name}</p>
                  {d.segment && (
                    <span className="type-caption text-brand-muted">{segLabel(d.segment)}</span>
                  )}
                </div>
                <span className="type-body text-brand-primary tabular-nums font-semibold whitespace-nowrap">{fmtSum(d.amount)}</span>
                <ArrowUpRight size={14} className="text-brand-muted opacity-0 coarse:opacity-100 group-hover:opacity-100 transition-opacity" />
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function MiniTable({
  firstCol,
  rows,
}: {
  firstCol: string;
  rows: { key: string; label: string; count: number; amount: number; href?: string }[];
}) {
  if (rows.length === 0) {
    return <p className="type-caption text-brand-muted">—</p>;
  }
  return (
    <div>
      <div className="flex items-center gap-3 mb-1 px-2 type-hint text-brand-muted uppercase tracking-wider">
        <span className="flex-1 truncate">{firstCol}</span>
        <span className="w-12 shrink-0 text-right">Сделок</span>
        <span className="w-24 shrink-0 text-right">Сумма</span>
      </div>
      <ul className="flex flex-col">
        {rows.map((r) => {
          const inner = (
            <>
              <span className="flex-1 type-body text-brand-primary truncate group-hover:text-brand-accent transition-colors">
                {r.label}
              </span>
              <span className="w-12 shrink-0 text-right type-body text-brand-primary tabular-nums">{r.count}</span>
              <span className="w-24 shrink-0 text-right type-body text-brand-primary tabular-nums whitespace-nowrap">{fmtSum(r.amount)}</span>
            </>
          );
          return (
            <li key={r.key}>
              {r.href ? (
                <Link
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  href={r.href as any}
                  className="group flex items-center gap-3 -mx-2 px-2 py-1.5 rounded-lg hover:bg-brand-bg transition-colors"
                >
                  {inner}
                </Link>
              ) : (
                <div className="flex items-center gap-3 px-2 py-1.5">{inner}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Kpi({
  icon, label, value, note, accent, danger,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  note: string;
  accent?: boolean;
  danger?: boolean;
}) {
  const wrapBg = accent
    ? "bg-brand-soft border border-brand-accent/20"
    : danger
    ? "bg-rose/5 border border-rose/15"
    : "bg-white border border-brand-border";
  const valueColor = accent ? "text-brand-accent-text" : danger ? "text-rose" : "text-brand-primary";
  return (
    <div className={`${wrapBg} rounded-card p-4 flex flex-col gap-1`}>
      <div className="flex items-center gap-2">
        <span className="text-brand-muted">{icon}</span>
        <span className="type-caption text-brand-muted uppercase tracking-wider font-semibold">{label}</span>
      </div>
      <p className={`type-kpi-number tabular-nums ${valueColor}`}>{value}</p>
      <p className="type-caption text-brand-muted">{note}</p>
    </div>
  );
}
