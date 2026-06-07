"use client";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import { useTeamWorkload } from "@/lib/hooks/use-team-workload";

function fmtSum(n: number): string {
  if (!n) return "—";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n) + " ₽";
}

export function WorkloadTable() {
  const { data, isLoading, isError } = useTeamWorkload();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }
  if (isError || !data) {
    return <div className="text-sm text-muted-2 py-10">Не удалось загрузить данные.</div>;
  }

  return (
    <div className="overflow-x-auto rounded-card border border-black/5 bg-white">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-black/5 text-left text-xs text-muted-2">
            <th className="px-4 py-3 font-semibold sticky left-0 z-10 bg-white">Менеджер</th>
            {data.stages.map((s) => (
              <th key={s.id} className="px-3 py-3 font-semibold whitespace-nowrap">
                {s.name}
              </th>
            ))}
            <th className="px-3 py-3 font-semibold">Итого</th>
            <th className="px-3 py-3 font-semibold">Зависшие</th>
          </tr>
        </thead>
        <tbody>
          {data.managers.map((m) => (
            <tr key={m.user_id} className="border-b border-black/5 hover:bg-black/[0.02]">
              <td className="px-4 py-3 font-medium sticky left-0 z-10 bg-white">
                <Link
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  href={`/pipeline?assigned_to=${m.user_id}` as any}
                  className="hover:underline text-brand-accent-text"
                >
                  {m.name}
                </Link>
              </td>
              {data.stages.map((s) => {
                const cell = m.by_stage[s.id];
                return (
                  <td key={s.id} className="px-3 py-3 whitespace-nowrap">
                    {cell ? (
                      <>
                        <span className="font-semibold">{cell.count}</span>
                        <span className="text-xs text-muted-2 ml-1">
                          {fmtSum(cell.sum_amount)}
                        </span>
                      </>
                    ) : (
                      <span className="text-muted-3">—</span>
                    )}
                  </td>
                );
              })}
              <td className="px-3 py-3 whitespace-nowrap">
                <span className="font-semibold">{m.open_count}</span>
                <span className="text-xs text-muted-2 ml-1">{fmtSum(m.pipeline_sum)}</span>
              </td>
              <td className="px-3 py-3">
                {m.stuck_count > 0 ? (
                  <Link
                    // filter=rotting is a no-op until the pipeline gains a rotting quick-filter
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    href={`/pipeline?assigned_to=${m.user_id}&filter=rotting` as any}
                    className="font-semibold text-warning hover:underline"
                  >
                    {m.stuck_count}
                  </Link>
                ) : (
                  <span className="text-muted-3">0</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
