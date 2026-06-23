"use client";

// /team/[user_id] — per-manager deep-dive for admins/heads.
// Top: identity header. Middle: active-deal portfolio (period-independent).
// Bottom: activity for the chosen period (КП / pool / moves / tasks) with a
// daily trend chart. The old duplicate «Лиды по этапам» block was dropped —
// it repeated the portfolio's «По этапам». Admin/head only.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ChevronLeft, ExternalLink, Loader2, Activity } from "lucide-react";

import { useMe } from "@/lib/hooks/use-me";
import { useManagerStats } from "@/lib/hooks/use-team-stats";
import { ManagerPortfolio } from "@/components/team/ManagerPortfolio";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { Badge } from "@/components/ui/Badge";
import type { TeamPeriod, TeamDailyRow } from "@/lib/types";

const PERIODS: { value: TeamPeriod; label: string }[] = [
  { value: "today", label: "Сегодня" },
  { value: "week", label: "Неделя" },
  { value: "month", label: "Месяц" },
];

const ROLE_LABEL: Record<string, string> = {
  admin: "Админ",
  head: "Руководитель",
  manager: "Менеджер",
};

const AVATAR_COLORS = [
  "bg-brand-accent",
  "bg-success",
  "bg-warning",
  "bg-rose",
  "bg-brand-primary",
];

function colorFor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function initialsOf(name: string, email: string): string {
  const src = (name || email || "?").trim();
  const parts = src.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return src.slice(0, 2).toUpperCase();
}

function shortDate(iso: string | undefined): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" }).format(new Date(iso));
}

function fullDay(iso: string): string {
  return new Intl.DateTimeFormat("ru-RU", { weekday: "short", day: "numeric", month: "long" }).format(
    new Date(iso),
  );
}

export default function ManagerStatsPage() {
  const me = useMe();
  const router = useRouter();
  const params = useParams<{ user_id: string }>();
  const userId = params?.user_id ?? null;
  const [period, setPeriod] = useState<TeamPeriod>("week");
  const stats = useManagerStats(userId, period);

  useEffect(() => {
    if (me.data && me.data.role !== "admin" && me.data.role !== "head") {
      router.replace("/today");
    }
  }, [me.data, router]);

  if (me.isLoading || !me.data) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 size={20} className="animate-spin text-brand-muted" />
      </div>
    );
  }
  if (me.data.role !== "admin" && me.data.role !== "head") return null;

  const name = stats.data?.name ?? "…";
  const email = stats.data?.email ?? "";
  const role = stats.data?.role ?? "";

  return (
    <div className={pageContainerVariants({ surface: "detail" })}>
      <Link
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        href={"/team" as any}
        className="inline-flex items-center gap-1 type-caption font-medium text-brand-muted hover:text-brand-primary mb-4 transition-colors"
      >
        <ChevronLeft size={14} />
        Назад к команде
      </Link>

      {/* Identity header */}
      <header className="bg-white border border-brand-border rounded-card p-5 sm:p-6 mb-6">
        <div className="flex flex-wrap items-center gap-4">
          <span
            className={`shrink-0 w-14 h-14 rounded-full flex items-center justify-center text-white text-lg font-bold ${colorFor(
              email || name,
            )}`}
          >
            {initialsOf(name, email)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="type-section-title text-brand-primary">{name}</h1>
              {role && <Badge variant="accent">{ROLE_LABEL[role] ?? role}</Badge>}
            </div>
            {email && <p className="type-caption font-mono text-brand-muted mt-1">{email}</p>}
          </div>
          {userId && (
            <Link
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              href={`/pipeline?assigned_to=${userId}` as any}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-brand-panel border border-brand-border type-caption font-semibold text-brand-primary hover:bg-brand-border transition-colors"
            >
              Открыть в воронке <ExternalLink size={13} />
            </Link>
          )}
        </div>
      </header>

      {/* Active-deal portfolio — KPIs, segments, stages, priority, top deals */}
      <section className="mb-8">
        <ManagerPortfolio userId={userId} />
      </section>

      {/* Activity for the selected period */}
      <section>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-brand-muted" />
            <h2 className="type-card-title text-brand-primary">Активность</h2>
            {stats.data && (
              <span className="type-hint text-brand-muted">
                {shortDate(stats.data.from)} – {shortDate(stats.data.to)}
              </span>
            )}
          </div>
          <div className="flex gap-1 bg-brand-panel rounded-full p-1">
            {PERIODS.map((pr) => (
              <button
                key={pr.value}
                type="button"
                aria-pressed={period === pr.value}
                onClick={() => setPeriod(pr.value)}
                className={
                  "px-3 py-1.5 rounded-full type-caption font-semibold transition-colors " +
                  (period === pr.value
                    ? "bg-white text-brand-primary"
                    : "text-brand-muted hover:text-brand-primary")
                }
              >
                {pr.label}
              </button>
            ))}
          </div>
        </div>

        {stats.isLoading && (
          <div className="bg-white border border-brand-border rounded-card p-6 animate-pulse h-48" />
        )}

        {stats.isError && (
          <p className="type-caption text-rose py-8 text-center">Не удалось загрузить активность.</p>
        )}

        {stats.data && (
          <div className="bg-white border border-brand-border rounded-card p-5 sm:p-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              <ActivityKpi label="КП отправлено" value={stats.data.stats.kp_sent} />
              <ActivityKpi label="Взято из пула" value={stats.data.stats.leads_taken_from_pool} />
              <ActivityKpi label="Продвинуто сделок" value={stats.data.stats.leads_moved} />
              <ActivityKpi label="Задач закрыто" value={stats.data.stats.tasks_completed} />
            </div>

            {stats.data.daily.length > 1 ? (
              <div className="mt-6 pt-5 border-t border-brand-border">
                <p className="type-caption text-brand-muted mb-3">Активность по дням</p>
                <ActivityTrend daily={stats.data.daily} />
              </div>
            ) : (
              <p className="type-hint text-brand-muted mt-5 pt-5 border-t border-brand-border">
                График по дням появляется для периодов «Неделя» и «Месяц».
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function ActivityKpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col">
      <p className="type-kpi-number text-brand-primary tabular-nums">{value}</p>
      <p className="type-caption text-brand-muted mt-0.5">{label}</p>
    </div>
  );
}

function ActivityTrend({ daily }: { daily: TeamDailyRow[] }) {
  const data = daily.map((d) => ({
    date: d.date,
    total: d.kp_sent + d.leads_taken_from_pool + d.leads_moved + d.tasks_completed,
  }));
  const max = Math.max(1, ...data.map((d) => d.total));
  const sum = data.reduce((acc, d) => acc + d.total, 0);
  const peak = Math.max(0, ...data.map((d) => d.total));

  return (
    <div>
      <div className="flex items-end gap-1 h-24">
        {data.map((d) => {
          const day = new Date(d.date);
          const weekend = day.getDay() === 0 || day.getDay() === 6;
          const pct = (d.total / max) * 100;
          return (
            <div
              key={d.date}
              className="flex-1 min-w-0 flex flex-col justify-end h-full"
              title={`${fullDay(d.date)} · ${d.total}`}
            >
              <div
                className={`w-full rounded-t-sm transition-opacity hover:opacity-70 ${
                  d.total === 0
                    ? "bg-brand-border/60"
                    : weekend
                      ? "bg-brand-accent/40"
                      : "bg-brand-accent"
                }`}
                style={{ height: `${d.total === 0 ? 3 : Math.max(pct, 8)}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between mt-2">
        <span className="type-hint text-brand-muted">{shortDate(data[0]?.date)}</span>
        <span className="type-hint text-brand-muted">{shortDate(data[data.length - 1]?.date)}</span>
      </div>
      <p className="type-caption text-brand-muted mt-3">
        Всего за период: <span className="text-brand-primary font-semibold tabular-nums">{sum}</span>{" "}
        действий · пик <span className="text-brand-primary font-semibold tabular-nums">{peak}</span> в
        день
      </p>
    </div>
  );
}
