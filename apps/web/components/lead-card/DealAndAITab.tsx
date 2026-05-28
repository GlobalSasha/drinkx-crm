"use client";
import { useState } from "react";
import {
  Sparkles,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useLatestEnrichment, useTriggerEnrichment } from "@/lib/hooks/use-enrichment";
import { ApiError } from "@/lib/api-client";
import type { LeadOut } from "@/lib/types";
import { C } from "@/lib/design-system";
import { SourceSection } from "./SourceSection";
import { LeadInfoBlock } from "./LeadInfoBlock";

interface Props {
  lead: LeadOut;
}

function asList(v: unknown): string[] {
  if (!v) return [];
  if (Array.isArray(v)) {
    return v.filter((x) => typeof x === "string" && x.trim()).map((x) => String(x));
  }
  if (typeof v === "string" && v.trim()) return [v];
  return [];
}

function asText(v: unknown): string {
  if (!v) return "";
  if (Array.isArray(v))
    return v.filter((x) => typeof x === "string" && x.trim()).join(", ");
  if (typeof v === "string") return v;
  return "";
}

export function DealAndAITab({ lead }: Props) {
  const ai = (lead.ai_data ?? {}) as Record<string, unknown>;
  const hasAiData = Object.keys(ai).length > 0 && Boolean(ai.company_profile || ai.company_overview);

  // AI narrative for the "Информация" card. City / website / formats are
  // intentionally dropped here — they now live in the editable property
  // table inside LeadInfoBlock (no more duplicate "О компании" block).
  const description =
    asText(ai.company_profile) || asText(ai.company_overview) || "";
  const networkScale = asText(ai.network_scale ?? ai.scale_signals);
  const formats = asList(ai.formats);
  const formatsText = formats.length > 0 ? formats.join(" · ") : asText(ai.formats);
  const subtitle = [formatsText, networkScale].filter(Boolean).join(" · ");

  return (
    <div className="space-y-4">
      {/* === Информация: AI narrative + editable property table === */}
      <LeadInfoBlock
        lead={lead}
        description={description || undefined}
        subtitle={subtitle || undefined}
      />

      {/* === Источник (only for form-sourced leads) === */}
      <SourceSection lead={lead} />

      {/* === AI Бриф === */}
      <AIBriefCard lead={lead} hasAiData={hasAiData} ai={ai} />
    </div>
  );
}

function AIBriefCard({
  lead,
  hasAiData,
  ai,
}: {
  lead: LeadOut;
  hasAiData: boolean;
  ai: Record<string, unknown>;
}) {
  const { data: run } = useLatestEnrichment(lead.id);
  const trigger = useTriggerEnrichment(lead.id);
  const [toast, setToast] = useState<string | null>(null);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  }

  function handleRun(mode: "full" | "append" | "lightweight") {
    trigger.mutate(mode, {
      onSuccess: () => {
        showToast("AI Бриф в очереди — обычно 5–10 сек");
      },
      onError: (err) => {
        if (err instanceof ApiError && err.status === 409) {
          showToast("Enrichment уже запущен");
        } else {
          showToast("Не удалось запустить enrichment");
        }
      },
    });
  }

  const isRunning = run?.status === "running" || trigger.isPending;

  const coffee = asList(ai.coffee_signals);
  const growth = asList(ai.growth_signals);
  const triggers = asList(ai.sales_triggers); // legacy prototype key
  const entryRoute = asText(ai.entry_route) || asList(ai.next_steps).join(" · ");
  const sources = asList(ai.sources_used);
  const sourceLabel = run?.provider || (hasAiData ? "База знаний" : "AI не запускали");

  return (
    <section className="bg-white rounded-2xl border border-brand-border p-5">
      <header className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-warning" />
          <h2 className={`type-card-title font-bold ${C.color.text}`}>AI Бриф</h2>
          <span className={`type-caption ${C.color.muted} font-mono`}>
            · {sourceLabel}
          </span>
        </div>
        {hasAiData ? (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleRun("lightweight")}
              disabled={isRunning}
              title="Бесплатное обновление: новости отрасли + сайт + вакансии, без Brave"
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 type-body font-semibold ${C.button.ghost} disabled:opacity-50 transition-opacity`}
            >
              Обновить (быстро)
            </button>
            <button
              type="button"
              onClick={() => handleRun("append")}
              disabled={isRunning}
              className={`inline-flex items-center gap-1.5 px-4 py-1.5 type-body font-semibold ${C.button.ghost} disabled:opacity-50 transition-opacity`}
            >
              {isRunning ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
              Дополнить
            </button>
          </div>
        ) : null}
      </header>

      {!hasAiData ? (
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <Sparkles size={32} className="text-warning mb-3" />
          <p className={`type-caption font-semibold ${C.color.text} mb-1`}>
            Бриф пока пуст
          </p>
          <p className={`type-caption ${C.color.muted} mb-5 max-w-sm`}>
            Запустите enrichment — AI соберёт данные из Brave, HH.ru и сайта
            компании, заполнит обзор, сигналы и следующий шаг.
          </p>
          <button
            type="button"
            onClick={() => handleRun("full")}
            disabled={isRunning}
            className="inline-flex items-center gap-2 px-5 py-2 type-body font-semibold bg-brand-accent text-white rounded-full disabled:opacity-50 transition-opacity"
          >
            {isRunning ? (
              <>
                <Loader2 size={14} className="animate-spin" /> Идёт enrichment…
              </>
            ) : (
              <>
                <Sparkles size={14} /> Запустить enrichment
              </>
            )}
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {coffee.length > 0 && (
            <Block title="Кофе / foodservice сигналы" items={coffee} />
          )}
          {growth.length > 0 && (
            <Block title="Growth signals" items={growth} />
          )}
          {triggers.length > 0 && (
            <Block title="Sales triggers" items={triggers} />
          )}
          {entryRoute && (
            <Block title="Маршрут входа" items={[entryRoute]} />
          )}

          {sources.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-3 border-t border-brand-border">
              {sources.map((s, i) => (
                <span
                  key={`${s}-${i}`}
                  className={`type-caption font-mono ${C.color.muted} bg-brand-panel px-2.5 py-1 rounded-full`}
                >
                  {s.length > 40 ? `${s.slice(0, 40)}…` : s}
                </span>
              ))}
            </div>
          )}

          <p className="type-hint text-brand-muted pt-1">
            Данные из базы. AI дополняет только пустые поля — существующие
            не перезаписываются.
          </p>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-ink text-white type-caption font-semibold px-5 py-2 rounded-full z-50">
          {toast}
        </div>
      )}
    </section>
  );
}

function Block({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="type-caption text-brand-muted mb-2">
        {title}
      </p>
      <ul className={`type-caption ${C.color.text} space-y-1.5 leading-relaxed`}>
        {items.map((it, i) => (
          <li key={i} className="flex gap-2">
            <span className={`${C.color.muted} shrink-0`}>·</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
