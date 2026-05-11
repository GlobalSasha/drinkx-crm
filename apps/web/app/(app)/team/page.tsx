"use client";

// /team — Sprint 3.4 G3. Manager activity dashboard.
// Gated to admin / head; managers get redirected to /today.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Users, Loader2 } from "lucide-react";

import { useMe } from "@/lib/hooks/use-me";
import { useTeamStats } from "@/lib/hooks/use-team-stats";
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
  const router = useRouter();
  const [period, setPeriod] = useState<TeamPeriod>("week");
  const stats = useTeamStats(period);

  // Redirect managers — admin/head only page.
  useEffect(() => {
    if (me.data && me.data.role !== "admin" && me.data.role !== "head") {
      router.replace("/today");
    }
  }, [me.data, router]);

  if (me.isLoading || !me.data) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }
  if (me.data.role !== "admin" && me.data.role !== "head") {
    return null; // redirect in flight
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
      <header className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div className="flex items-center gap-2">
          <Users size={20} className="text-muted" />
          <h1 className="text-xl font-extrabold tracking-tight">Команда</h1>
          {stats.data && (
            <span className="text-xs font-mono text-muted-3 ml-2">
              {formatRange(stats.data.from, stats.data.to)}
            </span>
          )}
        </div>

        <div className="flex gap-1 bg-canvas/80 rounded-pill p-1">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => setPeriod(p.value)}
              className={
                "px-3 py-1.5 rounded-pill text-xs font-semibold transition-colors " +
                (period === p.value
                  ? "bg-white shadow-sm text-ink"
                  : "text-muted-2 hover:text-ink")
              }
            >
              {p.label}
            </button>
          ))}
        </div>
      </header>

      {stats.isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white border border-black/5 rounded-2xl shadow-soft p-5 animate-pulse h-[148px]"
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
        <div className="bg-white border border-black/5 rounded-2xl p-12 text-center">
          <p className="text-sm text-muted-2">В команде пока нет участников.</p>
        </div>
      )}

      {stats.data && stats.data.managers.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {stats.data.managers.map((m) => (
            <ManagerCard key={m.user_id} m={m} />
          ))}
        </div>
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
      className="block bg-white border border-black/5 rounded-2xl shadow-soft p-5 hover:shadow-md transition-shadow"
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-full bg-brand-soft flex items-center justify-center shrink-0">
            <span className="text-sm font-bold text-brand-accent">{initial}</span>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink truncate">
              {m.name || m.email}
            </p>
            <p className="text-[11px] font-mono text-muted-3 truncate">
              {m.email}
            </p>
            <p className="text-[10px] font-mono text-muted-3 mt-0.5">
              последняя активность:{" "}
              {m.last_active_at ? relativeTime(m.last_active_at) : "никогда"}
            </p>
          </div>
        </div>
        <span className="shrink-0 text-[10px] font-mono uppercase tracking-[0.15em] text-muted-3 bg-canvas/80 rounded-pill px-2 py-1">
          {ROLE_LABEL[m.role] ?? m.role}
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2 border-t border-black/5 pt-4">
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
      <p className="text-xl font-extrabold tabular-nums text-ink">{value}</p>
      <p className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-3 mt-0.5">
        {label}
      </p>
    </div>
  );
}
