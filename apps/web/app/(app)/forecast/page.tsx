"use client";

import { useMemo } from "react";
import Link from "next/link";
import { TrendingUp, Wallet, AlertTriangle, Trophy, ArrowUpRight, Radio, Timer } from "lucide-react";
import { usePipelines } from "@/lib/hooks/use-pipelines";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useLeads } from "@/lib/hooks/use-leads";
import { useUtmStats } from "@/lib/hooks/use-utm-stats";
import { useStageDwell } from "@/lib/hooks/use-stage-dwell";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/Empty";
import { ChartContainer, ChartTooltip, BRAND_CHART_COLORS } from "@/components/ui/Chart";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid } from "recharts";
import { C } from "@/lib/design-system";

const FORECAST_LEADS_FILTER = { page_size: 500 } as const;

function fmtMoney(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "0 ₽";
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(0)} тыс ₽`;
  return `${Math.round(n)} ₽`;
}

export default function ForecastPage() {
  const { data: pipelines } = usePipelines();
  const { data: leadsData, isLoading } = useLeads(FORECAST_LEADS_FILTER);
  const { data: utmStats, isLoading: utmLoading } = useUtmStats();
  const { data: dwell, isLoading: dwellLoading } = useStageDwell();

  const { pipelineTotal, weightedTotal, atRiskTotal, atRiskDeals, wonRecent, stageBars } =
    useMemo(() => {
      // All pipelines, not just the first — stage ids are globally unique
      // UUIDs, so a flat map can't collide (plan 008).
      const stages = (pipelines ?? []).flatMap((p) => p.stages ?? []);
      const stageById = new Map(stages.map((s) => [s.id, s]));
      const leads = leadsData?.items ?? [];

      let pipelineTotal = 0;
      let weightedTotal = 0;
      let atRiskTotal = 0;
      const atRiskDeals: {
        id: string;
        company: string;
        amount: number;
        overdueDays: number;
        stageName: string;
      }[] = [];

      // Won in the last 90 days
      const NOW = Date.now();
      const NINETY_DAYS_AGO = NOW - 90 * 24 * 60 * 60 * 1000;
      let wonRecent = 0;

      // Stage bars (by money + by count)
      const stageBarMap = new Map<
        string,
        { name: string; position: number; total: number; count: number }
      >();
      stages
        .filter((s) => !s.is_won && !s.is_lost)
        .forEach((s) =>
          stageBarMap.set(s.id, {
            name: s.name,
            position: s.position,
            total: 0,
            count: 0,
          }),
        );

      for (const lead of leads) {
        const amount = Number(lead.deal_amount ?? 0);
        const stage = lead.stage_id ? stageById.get(lead.stage_id) : null;

        // Active pipeline = assigned + not in won/lost stage
        if (lead.assignment_status === "assigned" && stage && !stage.is_won && !stage.is_lost) {
          pipelineTotal += amount;
          weightedTotal += (amount * (stage.probability ?? 0)) / 100;

          const bar = stageBarMap.get(stage.id);
          if (bar) {
            bar.total += amount;
            bar.count += 1;
          }

          // At-risk: current_stage_days exceeds the stage's rot_days
          const days = lead.current_stage_days ?? 0;
          const rot = stage.rot_days ?? 0;
          if (rot > 0 && days > rot && amount > 0) {
            atRiskTotal += amount;
            atRiskDeals.push({
              id: lead.id,
              company: lead.company_name,
              amount,
              overdueDays: days - rot,
              stageName: stage.name,
            });
          }
        }

        // Won recent: any closed-won where the assigned_at fell in the 90-day window
        // (using last_activity_at as the closest proxy for "deal touched"; closed_at would
        // be more accurate but isn't reliably populated on every lead)
        if (stage?.is_won) {
          const touchedAt = lead.last_activity_at
            ? new Date(lead.last_activity_at).getTime()
            : null;
          if (touchedAt && touchedAt >= NINETY_DAYS_AGO) {
            wonRecent += amount;
          }
        }
      }

      atRiskDeals.sort((a, b) => b.amount - a.amount);

      const stageBars = Array.from(stageBarMap.values())
        .sort((a, b) => a.position - b.position)
        .map((b) => ({ name: b.name, total: b.total, count: b.count }));

      return {
        pipelineTotal,
        weightedTotal,
        atRiskTotal,
        atRiskDeals: atRiskDeals.slice(0, 10),
        wonRecent,
        stageBars,
      };
    }, [pipelines, leadsData]);

  return (
    <div className={pageContainerVariants({ surface: "data" })}>
      <PageHeader
        title="Прогноз"
        subtitle="Активная воронка, взвешенный прогноз по вероятностям этапов, риски и закрытые сделки."
      />

      {/* Truncation notice — the page sums only the fetched leads (capped),
          so a workspace with more leads gets a partial total (plan 008). */}
      {(leadsData?.total ?? 0) > (leadsData?.items?.length ?? 0) && (
        <p className="text-xs text-brand-muted mb-4 -mt-2">
          Показаны первые {leadsData?.items?.length ?? 0} из {leadsData?.total ?? 0} лидов — суммы частичные.
        </p>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">
        <Kpi
          icon={<Wallet size={16} />}
          label="Воронка"
          value={fmtMoney(pipelineTotal)}
          note="Сумма активных сделок"
          loading={isLoading}
        />
        <Kpi
          icon={<TrendingUp size={16} />}
          label="Взвешенный прогноз"
          value={fmtMoney(weightedTotal)}
          note="С учётом вероятности этапа"
          accent
          loading={isLoading}
        />
        <Kpi
          icon={<AlertTriangle size={16} className="text-rose" />}
          label="Под угрозой"
          value={fmtMoney(atRiskTotal)}
          note="Дольше срока на этапе"
          danger
          loading={isLoading}
        />
        <Kpi
          icon={<Trophy size={16} className="text-success" />}
          label="Закрыто за 90 дней"
          value={fmtMoney(wonRecent)}
          note="Выигранные сделки"
          loading={isLoading}
        />
      </div>

      {/* Stage funnel by money */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Воронка по сумме</CardTitle>
        </CardHeader>
        {stageBars.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"><Wallet /></EmptyMedia>
              <EmptyTitle>Нет активных сделок</EmptyTitle>
              <EmptyDescription>
                Заполните <code>deal_amount</code> на активных лидах — и здесь появится воронка по сумме.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <ChartContainer height={280} aria-label="Воронка по сумме сделок на каждом этапе">
            <BarChart data={stageBars} margin={{ top: 8, right: 12, bottom: 8, left: 12 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E3DC" vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: "#6B6B6B", fontSize: 11 }}
                axisLine={{ stroke: "#D6D4CE" }}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v) => fmtMoney(Number(v))}
                tick={{ fill: "#6B6B6B", fontSize: 11 }}
                axisLine={{ stroke: "#D6D4CE" }}
                tickLine={false}
                width={90}
              />
              <ChartTooltip
                formatter={(value: unknown) => [fmtMoney(Number(value)), "Сумма"]}
              />
              <Bar dataKey="total" fill={BRAND_CHART_COLORS[0]} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ChartContainer>
        )}
      </Card>

      {/* Acquisition channels — leads grouped by UTM source */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Каналы привлечения</CardTitle>
        </CardHeader>
        {!utmLoading && (utmStats?.length ?? 0) === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"><Radio /></EmptyMedia>
              <EmptyTitle>Пока нет данных по каналам</EmptyTitle>
              <EmptyDescription>
                Лиды с UTM-метками (из веб-форм с <code>?utm_source=…</code>)
                появятся здесь, сгруппированные по источнику.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="type-caption text-brand-muted uppercase tracking-wider">
                  <th className="font-semibold py-2 pr-3">Источник</th>
                  <th className="font-semibold py-2 px-3 text-right tabular-nums">Лиды</th>
                  <th className="font-semibold py-2 px-3 text-right tabular-nums">Сделки</th>
                  <th className="font-semibold py-2 px-3 text-right tabular-nums">Конверсия</th>
                  <th className="font-semibold py-2 pl-3 text-right tabular-nums">Выручка</th>
                </tr>
              </thead>
              <tbody>
                {utmLoading ? (
                  <tr>
                    <td colSpan={5} className="py-4 type-caption text-brand-muted">…</td>
                  </tr>
                ) : (
                  (utmStats ?? []).map((row) => {
                    const conv = row.leads > 0 ? Math.round((row.won / row.leads) * 100) : 0;
                    return (
                      <tr
                        key={row.source ?? "__none__"}
                        className="border-t border-brand-border"
                      >
                        <td className="py-2.5 pr-3 type-body text-brand-primary">
                          {row.source ?? (
                            <span className="text-brand-muted">Прямые / без UTM</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums type-body text-brand-primary">
                          {row.leads}
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums type-body text-brand-primary">
                          {row.won}
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums type-caption text-brand-muted">
                          {conv}%
                        </td>
                        <td className="py-2.5 pl-3 text-right tabular-nums type-body text-brand-primary font-semibold whitespace-nowrap">
                          {fmtMoney(Number(row.won_sum))}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Stage dwell — where deals get stuck */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Где застревают сделки</CardTitle>
        </CardHeader>
        {!dwellLoading &&
        (dwell ?? []).every((s) => s.completed_count === 0 && s.stuck_count === 0) ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"><Timer /></EmptyMedia>
              <EmptyTitle>Пока нет данных о переходах</EmptyTitle>
              <EmptyDescription>
                Как только сделки начнут двигаться по этапам, здесь появится
                средняя скорость и список «застрявших».
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="type-caption text-brand-muted uppercase tracking-wider">
                  <th className="font-semibold py-2 pr-3">Этап</th>
                  <th className="font-semibold py-2 px-3 text-right tabular-nums">Прошло</th>
                  <th className="font-semibold py-2 px-3 text-right tabular-nums">Медиана</th>
                  <th className="font-semibold py-2 px-3 text-right tabular-nums">p90</th>
                  <th className="font-semibold py-2 pl-3 text-right tabular-nums">Застряли</th>
                </tr>
              </thead>
              <tbody>
                {dwellLoading ? (
                  <tr>
                    <td colSpan={5} className="py-4 type-caption text-brand-muted">…</td>
                  </tr>
                ) : (
                  (dwell ?? []).map((s) => (
                    <tr key={s.stage_id} className="border-t border-brand-border">
                      <td className="py-2.5 pr-3 type-body text-brand-primary">{s.stage_name}</td>
                      <td className="py-2.5 px-3 text-right tabular-nums type-caption text-brand-muted">
                        {s.completed_count}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums type-body text-brand-primary">
                        {s.median_days != null ? `${s.median_days} дн` : "—"}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums type-caption text-brand-muted">
                        {s.p90_days != null ? `${s.p90_days} дн` : "—"}
                      </td>
                      <td className="py-2.5 pl-3 text-right tabular-nums">
                        {s.stuck_count > 0 ? (
                          <Badge variant="rose">{s.stuck_count}</Badge>
                        ) : (
                          <span className="type-caption text-brand-muted">0</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* At-risk deals list */}
      <Card>
        <CardHeader>
          <CardTitle>Под угрозой — топ-10</CardTitle>
        </CardHeader>
        {atRiskDeals.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon"><AlertTriangle /></EmptyMedia>
              <EmptyTitle>Рисков нет</EmptyTitle>
              <EmptyDescription>
                Никакие сделки не стоят на этапе дольше нормы. Так держать.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {atRiskDeals.map((d) => (
              <li key={d.id}>
                <Link
                  href={`/leads/${d.id}`}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-card bg-brand-bg hover:bg-brand-bg/70 transition-colors group"
                >
                  <div className="flex-1 min-w-0">
                    <p className="type-body text-brand-primary truncate">{d.company}</p>
                    <span className="inline-flex items-center gap-2 type-caption text-brand-muted mt-0.5">
                      <span>{d.stageName}</span>
                      <Badge variant="rose">
                        +{d.overdueDays} {d.overdueDays === 1 ? "день" : d.overdueDays < 5 ? "дня" : "дней"}
                      </Badge>
                    </span>
                  </div>
                  <span className="type-body text-brand-primary tabular-nums font-semibold whitespace-nowrap">
                    {fmtMoney(d.amount)}
                  </span>
                  <ArrowUpRight size={14} className="text-brand-muted opacity-0 group-hover:opacity-100 transition-opacity" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Kpi({
  icon, label, value, note, accent, danger, loading,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  note: string;
  accent?: boolean;
  danger?: boolean;
  loading?: boolean;
}) {
  const wrapBg = accent
    ? "bg-brand-soft border border-brand-accent/20"
    : danger
    ? "bg-rose/5 border border-rose/15"
    : "bg-white border border-brand-border";
  const valueColor = accent ? "text-brand-accent-text" : danger ? "text-rose" : C.color.text;
  return (
    <div className={`${wrapBg} rounded-card p-4 flex flex-col gap-1`}>
      <div className="flex items-center gap-2">
        <span className="text-brand-muted">{icon}</span>
        <span className="type-caption text-brand-muted uppercase tracking-wider font-semibold">
          {label}
        </span>
      </div>
      <p className={`type-kpi-number tabular-nums ${valueColor}`}>
        {loading ? "…" : value}
      </p>
      <p className="type-caption text-brand-muted">{note}</p>
    </div>
  );
}
