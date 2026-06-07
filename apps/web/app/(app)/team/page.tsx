"use client";

// /team — Sprint 3.4 G3. Manager activity dashboard.
// Gated to admin / head. Sprint 3.5: managers used to be silently redirected
// to /today, which left URL-typed visits looking broken. Now they see an
// explicit access-denied empty state with a route back.

import Link from "next/link";
import { useState } from "react";
import { Users, Loader2, ShieldAlert } from "lucide-react";

import { useMe } from "@/lib/hooks/use-me";
import { useTeamStats } from "@/lib/hooks/use-team-stats";
import { WorkloadTable } from "@/components/team/WorkloadTable";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from "@/components/ui/Empty";
import { relativeTime } from "@/lib/relative-time";
import type {
  TeamManagerStats,
  TeamPeriod,
} from "@/lib/types";

const PERIODS: { value: TeamPeriod; label: string }[] = [
  { value: "today", label: "Сегодня" },
  { value: "week",  label: "Неделя" },
  { value: "month", label: "Месяц" },
];

const VIEWS: { value: "activity" | "workload"; label: string }[] = [
  { value: "workload", label: "Manager's Dashboard" },
  { value: "activity", label: "Активность" },
];

const ROLE_LABEL: Record<string, string> = {
  admin: "Админ",
  head: "Руководитель",
  manager: "Менеджер",
};

function formatRange(from: string, to: string): string {
  const fmt = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
  });
  return `${fmt.format(new Date(from))} – ${fmt.format(new Date(to))}`;
}

export default function TeamPage() {
  const me = useMe();
  const [period, setPeriod] = useState<TeamPeriod>("week");
  const [view, setView] = useState<"activity" | "workload">("workload");
  const stats = useTeamStats(period);

  if (me.isLoading || !me.data) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }
  if (me.data.role !== "admin" && me.data.role !== "head") {
    return (
      <div className={pageContainerVariants({ surface: "reading" })}>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"><ShieldAlert /></EmptyMedia>
            <EmptyTitle>Раздел «Команда»</EmptyTitle>
            <EmptyDescription>
              Доступен руководителям и админам. Здесь видно активность всей команды:
              звонки, письма, движения по воронке, время отклика. Нужны метрики по себе —
              открой «Сегодня».
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Link
              href="/today"
              className="inline-flex items-center gap-2 text-sm font-medium text-brand-accent-text hover:underline"
            >
              ← Вернуться на «Сегодня»
            </Link>
          </EmptyContent>
        </Empty>
      </div>
    );
  }

  return (
    <div className={pageContainerVariants({ surface: "data" })}>
      <PageHeader
        icon={<Users size={20} />}
        title="Команда"
        actions={
          <>
            {view === "activity" && stats.data && (
              <span className="text-xs font-mono text-brand-muted">
                {formatRange(stats.data.from, stats.data.to)}
              </span>
            )}
            <div className="flex gap-1 bg-brand-panel rounded-full p-1">
              {VIEWS.map((v) => (
                <button
                  key={v.value}
                  type="button"
                  aria-pressed={view === v.value}
                  onClick={() => setView(v.value)}
                  className={
                    "px-3 py-1.5 rounded-full text-xs font-semibold transition-colors " +
                    (view === v.value
                      ? "bg-white text-brand-primary"
                      : "text-brand-muted hover:text-brand-primary")
                  }
                >
                  {v.label}
                </button>
              ))}
            </div>

            {view === "activity" && (
              <div className="flex gap-1 bg-brand-panel rounded-full p-1">
                {PERIODS.map((p) => (
                  <button
                    key={p.value}
                    type="button"
                    onClick={() => setPeriod(p.value)}
                    className={
                      "px-3 py-1.5 rounded-full text-xs font-semibold transition-colors " +
                      (period === p.value
                        ? "bg-white text-brand-primary"
                        : "text-brand-muted hover:text-brand-primary")
                    }
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            )}
          </>
        }
      />

      {view === "workload" && <WorkloadTable />}

      {view === "activity" && (
        <>
          {stats.isLoading && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="bg-white border border-brand-border rounded-card p-5 animate-pulse h-[148px]"
                />
              ))}
            </div>
          )}

          {stats.isError && (
            <p className="text-sm text-rose py-8 text-center">
              Не удалось загрузить статистику.
            </p>
          )}

          {stats.data && stats.data.managers.length === 0 && (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon"><Users /></EmptyMedia>
                <EmptyTitle>В команде пока нет участников</EmptyTitle>
                <EmptyDescription>
                  Пригласите коллег в настройках — и их активность появится здесь.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}

          {stats.data && stats.data.managers.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {stats.data.managers.map((m) => (
                <ManagerCard key={m.user_id} m={m} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ManagerCard({ m }: { m: TeamManagerStats }) {
  const initial = (m.name || m.email).slice(0, 1).toUpperCase();
  return (
    <Link
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      href={`/team/${m.user_id}` as any}
      className="block bg-white border border-brand-border rounded-card p-5 hover:border-brand-muted transition-colors"
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-full bg-brand-soft flex items-center justify-center shrink-0">
            <span className="text-sm font-bold text-brand-accent">{initial}</span>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-brand-primary truncate">
              {m.name || m.email}
            </p>
            <p className="text-xs font-mono text-brand-muted truncate">
              {m.email}
            </p>
            <p className="text-2xs font-mono text-brand-muted mt-0.5">
              последняя активность:{" "}
              {m.last_active_at ? relativeTime(m.last_active_at) : "никогда"}
            </p>
          </div>
        </div>
        <span className="shrink-0 text-2xs font-mono uppercase tracking-[0.15em] text-brand-muted bg-brand-panel rounded-full px-2 py-1">
          {ROLE_LABEL[m.role] ?? m.role}
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2 border-t border-brand-border pt-4">
        <Stat label="КП" value={m.stats.kp_sent} />
        <Stat label="Из пула" value={m.stats.leads_taken_from_pool} />
        <Stat label="Продвинуто" value={m.stats.leads_moved} />
        <Stat label="Задачи" value={m.stats.tasks_completed} />
      </div>
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center">
      <p className="text-xl font-bold tabular-nums text-brand-primary">{value}</p>
      <p className="text-2xs font-mono uppercase tracking-[0.15em] text-brand-muted mt-0.5">
        {label}
      </p>
    </div>
  );
}
