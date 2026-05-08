"use client";
// AISection — Sprint 2.4 G3.
//
// Admin-only view of the workspace AI knobs:
//   - daily budget cap (USD/day) with a live spend gauge
//   - primary LLM provider selector (deepseek / anthropic / gemini /
//     mimo)
//
// Persists into workspace.settings_json["ai"]. The fallback chain in
// app/enrichment/providers/factory.py still reads env in v1; wiring
// the workspace override into the chain is a 2.4+ polish carryover
// — surfaced in the card copy so the admin isn't confused when the
// model selector «doesn't take effect immediately».
import { useEffect, useState } from "react";
import { AlertTriangle, Bot, Loader2, Save, ShieldAlert } from "lucide-react";

import { ApiError } from "@/lib/api-client";
import { useMe } from "@/lib/hooks/use-me";
import {
  useAISettings,
  useUpdateAISettings,
} from "@/lib/hooks/use-settings-ai";

const MODEL_LABELS: Record<string, string> = {
  deepseek: "DeepSeek (default)",
  anthropic: "Anthropic Claude",
  gemini: "Google Gemini",
  mimo: "MiMo (бесплатный)",
};

export function AISection() {
  const me = useMe();
  const settingsQuery = useAISettings();
  const update = useUpdateAISettings();

  const isAdmin = me.data?.role === "admin";

  // Local form state — only flushed to the API on Save. Init from the
  // server payload once it arrives; an admin tweaking values shouldn't
  // race against a background refetch.
  const [budget, setBudget] = useState<string>("");
  const [model, setModel] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!settingsQuery.data) return;
    setBudget(settingsQuery.data.daily_budget_usd.toFixed(2));
    setModel(settingsQuery.data.primary_model);
  }, [settingsQuery.data]);

  if (!isAdmin) {
    return (
      <div className="bg-canvas/60 border border-black/5 rounded-2xl px-6 py-12 text-center">
        <ShieldAlert size={20} className="text-muted mx-auto mb-2" />
        <p className="text-sm text-muted">
          Доступ к настройкам AI — только у администратора.
        </p>
      </div>
    );
  }

  if (settingsQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }

  if (settingsQuery.isError || !settingsQuery.data) {
    return (
      <p className="text-sm text-rose py-8 text-center">
        Не удалось загрузить настройки AI.
      </p>
    );
  }

  const data = settingsQuery.data;
  const budgetNum = Number.parseFloat(budget);
  const budgetValid = Number.isFinite(budgetNum) && budgetNum >= 0;
  const dirty =
    budget !== data.daily_budget_usd.toFixed(2) || model !== data.primary_model;

  // Pct used today — clamp to 100 so the gauge bar doesn't overflow
  // on edge cases (e.g. budget set to 0 then re-enabled mid-day).
  const cap = data.daily_budget_usd;
  const spend = data.current_spend_usd_today;
  const pct =
    cap <= 0 ? 100 : Math.min(100, Math.round((spend / cap) * 100));
  const overBudget = pct >= 100;

  function onSave() {
    setError(null);
    if (!budgetValid) {
      setError("Бюджет должен быть числом ≥ 0.");
      return;
    }
    update.mutate(
      {
        daily_budget_usd: budgetNum,
        primary_model: model,
      },
      {
        onError: (err: ApiError) => {
          const detail =
            err.body && typeof err.body === "object"
              ? (err.body as { detail?: unknown }).detail
              : null;
          if (detail && typeof detail === "object" && "message" in detail) {
            setError(String((detail as { message: unknown }).message));
          } else {
            setError("Не удалось сохранить. Попробуйте ещё раз.");
          }
        },
      },
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-extrabold tracking-tight">AI</h2>
        <p className="text-xs text-muted-2 mt-0.5">
          Лимит расходов на исследования лидов и выбор основного провайдера.
          Настройки записываются, но fallback-цепочка в v1 ещё читает env —
          реальное переключение модели приедет в Sprint 2.4+.
        </p>
      </div>

      {/* Spend gauge card */}
      <div className="bg-white border border-black/5 rounded-2xl shadow-soft p-5">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-canvas flex items-center justify-center shrink-0">
            <Bot size={18} className="text-muted" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-extrabold text-ink">
                Дневной бюджет
              </h3>
              <span
                className={`text-[11px] font-mono ${
                  overBudget ? "text-rose" : "text-muted-2"
                }`}
              >
                {spend.toFixed(2)} / {cap.toFixed(2)} USD
              </span>
            </div>

            <div className="mt-3 h-2 bg-canvas rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${
                  overBudget
                    ? "bg-rose"
                    : pct > 80
                      ? "bg-warning"
                      : "bg-accent"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>

            {overBudget && (
              <p className="mt-2 text-[11px] text-rose flex items-center gap-1.5">
                <AlertTriangle size={11} />
                Бюджет на сегодня исчерпан — обогащение лидов приостановлено
                до завтра или повышения лимита.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Editor card */}
      <div className="bg-white border border-black/5 rounded-2xl shadow-soft p-5 space-y-4">
        <div>
          <label
            htmlFor="ai-budget"
            className="text-[11px] font-mono uppercase tracking-wide text-muted-3"
          >
            Лимит USD/день
          </label>
          <input
            id="ai-budget"
            type="number"
            min="0"
            step="0.5"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            className="mt-1 w-full max-w-[200px] bg-canvas border border-black/10 rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:border-accent"
          />
          <p className="text-[11px] text-muted-3 mt-1">
            При достижении лимита фоновые исследования останавливаются.
            Дневной счётчик сбрасывается в полночь UTC.
          </p>
        </div>

        <div>
          <label
            htmlFor="ai-model"
            className="text-[11px] font-mono uppercase tracking-wide text-muted-3"
          >
            Основная модель
          </label>
          <select
            id="ai-model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="mt-1 w-full max-w-[280px] bg-canvas border border-black/10 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-accent"
          >
            {data.available_models.map((m) => (
              <option key={m} value={m}>
                {MODEL_LABELS[m] ?? m}
              </option>
            ))}
          </select>
        </div>

        {error && <p className="text-xs text-rose">{error}</p>}

        <div className="flex items-center gap-2 pt-2">
          <button
            type="button"
            onClick={onSave}
            disabled={!dirty || !budgetValid || update.isPending}
            className="inline-flex items-center gap-1.5 bg-ink text-white rounded-pill px-4 py-2 text-sm font-semibold hover:bg-ink/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-300"
          >
            {update.isPending ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Save size={13} />
            )}
            Сохранить
          </button>
          {update.isSuccess && !dirty && (
            <span className="text-[11px] text-success font-mono">
              · сохранено
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
