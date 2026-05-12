"use client";

// /team/[user_id] — Sprint 3.4 G3. Per-manager activity breakdown
// with a daily table for the chosen period. Admin/head only.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ChevronLeft, Loader2 } from "lucide-react";

import { T } from "@/lib/design-system";
import { useMe } from "@/lib/hooks/use-me";
import { useManagerStats } from "@/lib/hooks/use-team-stats";
import type { TeamPeriod } from "@/lib/types";

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

function formatDay(iso: string): string {
  const d = new Date(iso);
  return new Intl.DateTimeFormat("ru-RU", {
    weekday: "short",
    day: "numeric",
    month: "long",
  }).format(d);
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
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }
  if (me.data.role !== "admin" && me.data.role !== "head") return null;

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">
      <Link
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        href={"/team" as any}
        className="inline-flex items-center gap-1 text-xs font-mono text-muted-2 hover:text-ink mb-4 transition-colors"
      >
        <ChevronLeft size={12} />
        Назад к команде
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className={T.heading}>
            {stats.data?.name ?? "…"}
          </h1>
          {stats.data && (
            <p className="text-xs font-mono text-muted-3 mt-0.5">
              {stats.data.email} ·{" "}
              {ROLE_LABEL[stats.data.role] ?? stats.data.role}
            </p>
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
        <div className="bg-white border border-black/5 rounded-2xl shadow-soft p-6 animate-pulse h-[260px]" />
      )}

      {stats.isError && (
        <p className="text-sm text-rose py-8 text-center">
          Не удалось загрузить статистику.
        </p>
      )}

      {stats.data && (
        <>
          {/* Total stats */}
          <div className="bg-white border border-black/5 rounded-2xl shadow-soft p-5 mb-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Stat label="КП" value={stats.data.stats.kp_sent} />
              <Stat label="Из пула" value={stats.data.stats.leads_taken_from_pool} />
              <Stat label="Продвинуто" value={stats.data.stats.leads_moved} />
              <Stat label="Задачи" value={stats.data.stats.tasks_completed} />
            </div>
          </div>

          {/* Daily table */}
          <div className="bg-white border border-black/5 rounded-2xl shadow-soft overflow-hidden">
            <table className="w-full text-left">
              <thead className="bg-canvas/60">
                <tr className="border-b border-black/5">
                  <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold`}>
                    Дата
                  </th>
                  <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold text-right w-[80px]`}>
                    КП
                  </th>
                  <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold text-right w-[80px]`}>
                    Из пула
                  </th>
                  <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold text-right w-[100px]`}>
                    Продвинуто
                  </th>
                  <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold text-right w-[80px]`}>
                    Задачи
                  </th>
                </tr>
              </thead>
              <tbody>
                {stats.data.daily.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center">
                      <p className="text-sm text-muted-2">
                        За этот период активности не было.
                      </p>
                    </td>
                  </tr>
                )}
                {stats.data.daily.map((d) => (
                  <tr key={d.date} className="border-b border-black/5 last:border-0 hover:bg-canvas/40">
                    <td className="px-4 py-2.5 align-middle">
                      <span className="text-sm text-ink">{formatDay(d.date)}</span>
                    </td>
                    <td className="px-4 py-2.5 align-middle text-right tabular-nums text-sm">
                      {d.kp_sent}
                    </td>
                    <td className="px-4 py-2.5 align-middle text-right tabular-nums text-sm">
                      {d.leads_taken_from_pool}
                    </td>
                    <td className="px-4 py-2.5 align-middle text-right tabular-nums text-sm">
                      {d.leads_moved}
                    </td>
                    <td className="px-4 py-2.5 align-middle text-right tabular-nums text-sm">
                      {d.tasks_completed}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center">
      <p className={`${T.metric} text-ink`}>{value}</p>
      <p className={`${T.mono} uppercase text-muted-3 mt-1`}>
        {label}
      </p>
    </div>
  );
}
