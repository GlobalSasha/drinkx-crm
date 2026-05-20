"use client";
// CostsSection — Sprint 4.0 G7. Admin-only LLM spend counter.
//
// Shows total AI spend + a per-provider breakdown for the chosen
// period (this month / last month / all time). Read from
// GET /admin/llm-costs?period=… — see app/admin (backend).
import { useState } from "react";
import { Coins, Loader2, ShieldAlert } from "lucide-react";

import { useMe } from "@/lib/hooks/use-me";
import { useLlmCosts, type CostPeriod } from "@/lib/hooks/use-llm-costs";

const PROVIDER_LABELS: Record<string, string> = {
  mimo: "MiMo",
  anthropic: "Anthropic Claude",
  gemini: "Google Gemini",
  deepseek: "DeepSeek",
};

const PERIODS: { key: CostPeriod; label: string }[] = [
  { key: "this_month", label: "Этот месяц" },
  { key: "last_month", label: "Прошлый месяц" },
  { key: "all", label: "Всё время" },
];

function fmt(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

export function CostsSection() {
  const me = useMe();
  const [period, setPeriod] = useState<CostPeriod>("this_month");
  const { data, isLoading } = useLlmCosts(period);

  const isAdmin = me.data?.role === "admin";

  if (me.isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="bg-canvas/60 border border-black/5 rounded-2xl px-6 py-12 text-center">
        <ShieldAlert size={20} className="text-muted mx-auto mb-2" />
        <p className="text-sm text-muted">
          Раздел доступен только администратору.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Coins size={18} className="text-brand-accent" />
        <h2 className="text-lg font-bold tracking-tight">Расходы на AI</h2>
      </div>

      {/* Period toggle */}
      <div className="inline-flex rounded-xl bg-black/5 p-1">
        {PERIODS.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => setPeriod(p.key)}
            className={
              "px-3 py-1.5 text-sm font-semibold rounded-lg transition-colors " +
              (period === p.key ? "bg-white text-ink shadow-soft" : "text-muted")
            }
          >
            {p.label}
          </button>
        ))}
      </div>

      {isLoading || !data ? (
        <div className="flex items-center gap-2 text-muted">
          <Loader2 size={16} className="animate-spin" /> Загрузка…
        </div>
      ) : (
        <>
          <div>
            <div className="text-sm text-muted">Всего на AI</div>
            <div className="text-3xl font-bold tracking-tight">
              {fmt(data.total_usd)}
            </div>
          </div>

          {data.by_provider.length === 0 ? (
            <p className="text-sm text-muted">Нет данных за период</p>
          ) : (
            <ul className="divide-y divide-black/5 rounded-2xl border border-black/5 bg-white">
              {data.by_provider.map((p) => (
                <li
                  key={p.provider}
                  className={
                    "flex items-center justify-between px-4 py-3 " +
                    (p.cost_usd === 0 ? "text-muted-3" : "")
                  }
                >
                  <span className="font-semibold">
                    {PROVIDER_LABELS[p.provider] ?? p.provider}
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="text-sm text-muted">{p.calls} выз.</span>
                    <span className="font-mono">{fmt(p.cost_usd)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
