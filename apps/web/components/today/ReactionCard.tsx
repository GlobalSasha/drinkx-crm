"use client";

// «Скорость реакции» on the head/admin /today: how fast someone first touched
// an incoming lead (web form or paid source) — last 30 days vs the 30 before —
// and the incoming leads still waiting. Data: `reaction` of GET /company/inflow.
// Only what is recorded in the CRM counts: a call made from a personal phone
// and never logged looks like no reaction, and the note says so.

import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, ChevronRight } from "lucide-react";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { C } from "@/lib/design-system";
import { useCompanyInflow } from "@/lib/hooks/use-company";
import type { InflowReaction } from "@/lib/types";

export function formatWait(hours: number): string {
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} мин`;
  if (hours < 48) return `${Math.round(hours)} ч`;
  return `${Math.round(hours / 24)} дн.`;
}

export function ReactionCard() {
  const { data, isLoading, isError } = useCompanyInflow();

  return (
    <Card className="mb-5">
      <CardHeader>
        <CardTitle>Скорость реакции</CardTitle>
        <span className="type-hint not-italic text-brand-muted">заявки с сайта и рекламы · 30 дней</span>
      </CardHeader>
      {isError ? (
        <p className="type-body text-rose py-6 text-center">Не удалось загрузить — обновите страницу.</p>
      ) : isLoading || !data ? (
        <div className="h-24 rounded-lg bg-brand-panel animate-pulse" aria-hidden />
      ) : (
        <ReactionBody reaction={data.reaction} />
      )}
    </Card>
  );
}

function ReactionBody({ reaction }: { reaction: InflowReaction }) {
  const { current: cur, previous: prev } = reaction;

  if (cur.total === 0) {
    return <p className="type-body text-brand-muted py-6 text-center">За 30 дней заявок с сайта и рекламы не было.</p>;
  }

  // Lower is better: a faster median is the good direction.
  const medianDelta =
    cur.median_hours != null && prev.median_hours != null && prev.median_hours > 0
      ? Math.round(((cur.median_hours - prev.median_hours) / prev.median_hours) * 100)
      : null;
  const share = Math.round((cur.touched / cur.total) * 100);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-lg bg-brand-bg p-4">
          <span className="type-caption text-brand-muted">До первого действия</span>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="type-kpi-number text-brand-primary">
              {cur.median_hours != null ? formatWait(cur.median_hours) : "—"}
            </span>
            {medianDelta != null && medianDelta !== 0 && (
              <span
                className={`inline-flex items-center type-label tabular-nums ${medianDelta < 0 ? "text-success" : "text-rose"}`}
              >
                {medianDelta < 0 ? <ArrowDownRight size={14} /> : <ArrowUpRight size={14} />}
                {medianDelta > 0 ? "+" : ""}
                {medianDelta}%
              </span>
            )}
          </div>
          <span className="type-hint not-italic text-brand-muted">
            медиана{prev.median_hours != null ? ` · раньше ${formatWait(prev.median_hours)}` : ""}
          </span>
        </div>

        <div className="rounded-lg bg-brand-bg p-4">
          <span className="type-caption text-brand-muted">Отреагировали</span>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="type-kpi-number text-brand-primary">{cur.touched}</span>
            <span className="type-label text-brand-muted tabular-nums">из {cur.total}</span>
          </div>
          <span className={`type-hint not-italic ${share < 50 ? "text-rose" : "text-brand-muted"}`}>
            {share}% заявок
          </span>
        </div>

        <div className="rounded-lg bg-brand-bg p-4">
          <span className="type-caption text-brand-muted">В течение часа</span>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="type-kpi-number text-brand-primary">{cur.within_hour}</span>
            <span className="type-label text-brand-muted tabular-nums">из {cur.total}</span>
          </div>
          <span className="type-hint not-italic text-brand-muted">раньше {prev.within_hour} из {prev.total}</span>
        </div>
      </div>

      <div>
        <div className="flex items-baseline justify-between gap-3 mb-2">
          <h3 className="type-card-title text-brand-primary">Ждут ответа</h3>
          <span className={`type-label tabular-nums ${reaction.waiting_count > 0 ? "text-rose" : "text-success"}`}>
            {reaction.waiting_count > 0 ? reaction.waiting_count : "никто"}
          </span>
        </div>
        {reaction.waiting.length > 0 ? (
          <ul>
            {reaction.waiting.map((w) => (
              <li key={w.lead_id} className="border-t border-brand-border first:border-t-0">
                <Link
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  href={`/leads/${w.lead_id}` as any}
                  className={`flex items-center gap-3 py-2.5 rounded-md hover:bg-brand-bg transition-colors ${C.focusRing}`}
                >
                  <span className="flex-1 min-w-0">
                    <span className="block truncate type-body text-brand-primary">{w.company_name}</span>
                    <span className="block type-hint not-italic text-brand-muted">{w.source}</span>
                  </span>
                  <span className="shrink-0 type-label tabular-nums text-rose">ждёт {formatWait(w.hours)}</span>
                  <ChevronRight size={16} className="shrink-0 text-brand-muted" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="type-body text-brand-muted">Все заявки за 30 дней получили ответ.</p>
        )}
        {reaction.waiting_count > reaction.waiting.length && (
          <p className="type-hint not-italic text-brand-muted mt-2">
            Показаны самые старые {reaction.waiting.length} из {reaction.waiting_count}.
          </p>
        )}
      </div>

      <p className="type-hint text-brand-muted">
        Реакция — первое, что человек сделал по заявке в CRM: комментарий, задача, звонок, письмо или смена
        этапа. Звонок с личного телефона, не записанный в карточку, сюда не попадает. Автоматические задачи не
        считаются.
      </p>
    </div>
  );
}
