"use client";
// «Скорость обработки» on the head/admin /today: per manager, today and this
// week. Web requests count until the first comment; leads a manager created
// count until the first comment after 30 minutes (the note of the call that
// made them a lead is not handling). Leads handed out from the base are left
// out. Time is shown in working hours (Mon–Fri 9–19 MSK) and calendar hours.
// Data: GET /company/manager-speed.
import { useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { C } from "@/lib/design-system";
import { useCompanyManagerSpeed } from "@/lib/hooks/use-company";
import { formatWait } from "@/components/today/ReactionCard";
import type { ManagerSpeedRow, SpeedStats } from "@/lib/types";

type Period = "today" | "week";

// A request that came at night and was answered before 9:00 took zero working
// hours — say so instead of rounding up to «1 мин».
function fmt(hours: number): string {
  return hours === 0 ? "0 мин" : formatWait(hours);
}

const PERIODS: { key: Period; label: string }[] = [
  { key: "today", label: "Сегодня" },
  { key: "week", label: "Неделя" },
];

export function ManagerSpeedCard() {
  const { data, isLoading, isError } = useCompanyManagerSpeed();
  const [period, setPeriod] = useState<Period>("week");

  return (
    <Card className="mb-5">
      <CardHeader>
        <div>
          <CardTitle>Скорость обработки</CardTitle>
          <span className="type-hint not-italic text-brand-muted">
            до комментария · рабочие часы пн–пт 9–19 и календарные
          </span>
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
      </CardHeader>
      {isError ? (
        <p className="type-body text-rose py-6 text-center">Не удалось загрузить — обновите страницу.</p>
      ) : isLoading || !data ? (
        <div className="h-24 rounded-lg bg-brand-panel animate-pulse" aria-hidden />
      ) : data.managers.length === 0 ? (
        <p className="type-body text-brand-muted py-6 text-center">
          На этой неделе новых заявок с сайта и своих лидов нет.
        </p>
      ) : (
        <div className="space-y-6">
          {data.managers.map((m) => (
            <ManagerBlock key={m.manager_id} row={m} period={period} />
          ))}
        </div>
      )}
    </Card>
  );
}

function ManagerBlock({ row, period }: { row: ManagerSpeedRow; period: Period }) {
  const stats = row[period];
  return (
    <section aria-label={row.name}>
      <h3 className="type-card-title text-brand-primary mb-2">{row.name}</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <SpeedTile title="Заявки с сайта" stats={stats.forms} countLabel="пришло" />
        <SpeedTile title="Свои лиды" stats={stats.own} countLabel="заведено" />
      </div>
      {period === "week" && row.hanging.length > 0 && (
        <details className="mt-3">
          <summary className={`cursor-pointer type-label text-rose ${C.focusRing} rounded-md`}>
            Висят дольше всех
          </summary>
          <ul className="mt-2">
            {row.hanging.map((h) => (
              <li key={h.lead_id} className="border-t border-brand-border first:border-t-0">
                <Link
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  href={`/leads/${h.lead_id}` as any}
                  className={`flex items-center gap-3 py-2 rounded-md hover:bg-brand-bg transition-colors ${C.focusRing}`}
                >
                  <span className="flex-1 min-w-0">
                    <span className="block truncate type-body text-brand-primary">{h.company_name}</span>
                    <span className="block type-hint not-italic text-brand-muted">
                      {h.kind === "form" ? "Заявка с сайта" : "Свой лид"}
                    </span>
                  </span>
                  <span className="shrink-0 type-label tabular-nums text-rose">висит {formatWait(h.hours)}</span>
                  <ChevronRight size={16} className="shrink-0 text-brand-muted" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function SpeedTile({
  title,
  stats,
  countLabel,
}: {
  title: string;
  stats: SpeedStats;
  countLabel: string;
}) {
  return (
    <div className="rounded-lg bg-brand-bg p-4">
      <span className="type-caption text-brand-muted">{title}</span>
      <div className="mt-1 flex items-baseline gap-2 flex-wrap">
        <span className="type-kpi-number text-brand-primary">
          {stats.median_work_hours != null ? `раб. ${fmt(stats.median_work_hours)}` : "—"}
        </span>
        {stats.median_hours != null && (
          <span className="type-label text-brand-muted tabular-nums">
            кален. {fmt(stats.median_hours)}
          </span>
        )}
      </div>
      <p className="type-hint not-italic text-brand-muted tabular-nums">
        {countLabel} {stats.total} · обработано {stats.handled}
        {" · "}
        <span className={stats.hanging > 0 ? "text-rose" : undefined}>висят {stats.hanging}</span>
      </p>
    </div>
  );
}
