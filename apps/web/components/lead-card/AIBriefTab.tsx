"use client";

import { useState } from "react";
import { Loader2, AlertTriangle, Sparkles, RefreshCw } from "lucide-react";
import { useLatestEnrichment, useTriggerEnrichment } from "@/lib/hooks/use-enrichment";
import { ApiError } from "@/lib/api-client";
import type { ResearchOutput, DecisionMakerHint, EnrichmentRun } from "@/lib/types";

interface Props {
  leadId: string;
}

export function AIBriefTab({ leadId }: Props) {
  const { data: run, isLoading } = useLatestEnrichment(leadId);
  const trigger = useTriggerEnrichment(leadId);
  const [toast, setToast] = useState<string | null>(null);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  }

  function handleTrigger() {
    trigger.mutate(undefined, {
      onError: (err) => {
        if (err instanceof ApiError && err.status === 409) {
          showToast("Enrichment уже запущен");
        } else {
          showToast("Ошибка запуска enrichment");
        }
      },
    });
  }

  const isRunning = run?.status === "running" || trigger.isPending;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-ink">AI Brief</h3>
          {run && (
            <p className="font-mono text-[10px] text-muted-3 mt-0.5">
              {run.provider && run.model
                ? `${run.provider} · ${run.model}`
                : run.provider ?? ""}
              {run.duration_ms > 0 && ` · ${(run.duration_ms / 1000).toFixed(1)}s`}
              {Number(run.cost_usd) > 0 && ` · $${Number(run.cost_usd).toFixed(4)}`}
              {" · "}
              {new Date(run.started_at).toLocaleString("ru-RU", {
                day: "2-digit",
                month: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          )}
        </div>

        <button
          onClick={handleTrigger}
          disabled={isRunning}
          className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-accent text-white rounded-pill hover:bg-accent/90 disabled:opacity-60 disabled:cursor-not-allowed transition-all"
        >
          {isRunning ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Идёт enrichment…
            </>
          ) : run ? (
            <>
              <RefreshCw size={14} />
              Обновить
            </>
          ) : (
            <>
              <Sparkles size={14} />
              Запустить enrichment
            </>
          )}
        </button>
      </div>

      {/* Running skeleton */}
      {run?.status === "running" && (
        <RunningState startedAt={run.started_at} />
      )}

      {/* Failed banner */}
      {run?.status === "failed" && (
        <div className="bg-rose/5 border border-rose/20 rounded-2xl px-5 py-4">
          <div className="flex items-start gap-2 mb-3">
            <AlertTriangle size={15} className="text-rose mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-rose">Enrichment завершился с ошибкой</p>
              {run.error && (
                <p className="text-xs text-rose/80 mt-1 line-clamp-3">{run.error}</p>
              )}
            </div>
          </div>
          <button
            onClick={handleTrigger}
            disabled={trigger.isPending}
            className="text-xs font-semibold text-rose hover:underline disabled:opacity-50"
          >
            Попробовать снова
          </button>
        </div>
      )}

      {/* Result */}
      {run?.status === "succeeded" && run.result_json && (
        <ResultBody result={run.result_json} run={run} />
      )}

      {/* Empty state — no runs yet */}
      {!run && run !== undefined && (
        <EmptyState onTrigger={handleTrigger} isPending={trigger.isPending} />
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-ink text-white text-sm font-semibold px-5 py-2.5 rounded-pill shadow-soft z-50">
          {toast}
        </div>
      )}
    </div>
  );
}

// ---- sub-components ----

function RunningState({ startedAt }: { startedAt: string }) {
  const elapsed = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-2 italic animate-pulse">
        AI агент работает над компанией… ({elapsed} сек)
      </p>
      {[120, 80, 100, 60, 90].map((w, i) => (
        <div
          key={i}
          className="h-4 bg-black/5 rounded-lg animate-pulse"
          style={{ width: `${w}%` }}
        />
      ))}
    </div>
  );
}

function EmptyState({ onTrigger, isPending }: { onTrigger: () => void; isPending: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-4 text-center">
      <div className="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center">
        <Sparkles size={22} className="text-accent" />
      </div>
      <div>
        <p className="text-sm font-semibold text-ink mb-1">Нет данных AI enrichment</p>
        <p className="text-xs text-muted-2 max-w-xs">
          AI соберёт данные из Brave, HH.ru, сайта компании и подготовит профиль для переговоров.
        </p>
      </div>
      <button
        onClick={onTrigger}
        disabled={isPending}
        className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold bg-accent text-white rounded-pill hover:bg-accent/90 disabled:opacity-60 transition-all"
      >
        {isPending ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Sparkles size={14} />
        )}
        Запустить enrichment
      </button>
    </div>
  );
}

function ResultBody({ result, run }: { result: ResearchOutput; run: EnrichmentRun }) {
  const fitScore = result.fit_score ?? 0;
  const fitColor =
    fitScore >= 8
      ? "bg-yellow-400/20 text-yellow-700 border-yellow-400/30"
      : fitScore >= 5
      ? "bg-accent/10 text-accent border-accent/20"
      : "bg-black/5 text-muted border-black/10";

  const urgencyChip =
    result.urgency === "high"
      ? "bg-rose/10 text-rose border-rose/20"
      : result.urgency === "medium"
      ? "bg-warning/10 text-warning border-warning/20"
      : "bg-black/5 text-muted border-black/10";

  const urgencyLabel =
    result.urgency === "high"
      ? "Высокая срочность"
      : result.urgency === "medium"
      ? "Средняя срочность"
      : "Низкая срочность";

  return (
    <div className="space-y-6">
      {/* Fit score + urgency row */}
      <div className="flex items-center gap-3">
        <div
          className={`flex items-center justify-center w-14 h-14 rounded-2xl border text-2xl font-extrabold ${fitColor}`}
        >
          {fitScore}
        </div>
        <div>
          <p className="text-xs font-semibold text-muted-3 uppercase tracking-widest mb-1">
            Fit Score / 10
          </p>
          {result.urgency && (
            <span
              className={`text-xs font-semibold px-2.5 py-1 rounded-pill border ${urgencyChip}`}
            >
              {urgencyLabel}
            </span>
          )}
        </div>
      </div>

      {/* Company profile */}
      {result.company_profile && (
        <Section title="Профиль компании">
          <p className="text-sm text-ink/85 leading-relaxed">{result.company_profile}</p>
        </Section>
      )}

      {/* Scale / geo / formats grid */}
      {(result.network_scale || result.geography || result.formats) && (
        <Section title="Масштаб · География · Форматы">
          <div className="grid grid-cols-2 gap-3">
            {result.network_scale && (
              <InfoCell label="Сеть" value={result.network_scale} />
            )}
            {result.geography && (
              <InfoCell label="География" value={result.geography} />
            )}
            {result.formats && (
              <InfoCell label="Форматы" value={result.formats} />
            )}
          </div>
        </Section>
      )}

      {/* Coffee signals */}
      {result.coffee_signals && (
        <Section title="Coffee signals">
          <p className="text-sm text-ink/80 leading-relaxed">{result.coffee_signals}</p>
        </Section>
      )}

      {/* Growth / Risk signals */}
      {((result.growth_signals?.length ?? 0) > 0 || (result.risk_signals?.length ?? 0) > 0) && (
        <Section title="Сигналы роста и риска">
          <div className="grid grid-cols-2 gap-4">
            {(result.growth_signals?.length ?? 0) > 0 && (
              <div>
                <p className="text-[10px] font-mono uppercase tracking-widest text-success mb-2">
                  Рост
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {result.growth_signals.map((s, i) => (
                    <span
                      key={i}
                      className="text-xs px-2.5 py-1 rounded-pill bg-success/10 text-success border border-success/20"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {(result.risk_signals?.length ?? 0) > 0 && (
              <div>
                <p className="text-[10px] font-mono uppercase tracking-widest text-rose mb-2">
                  Риски
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {result.risk_signals.map((s, i) => (
                    <span
                      key={i}
                      className="text-xs px-2.5 py-1 rounded-pill bg-rose/10 text-rose border border-rose/20"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Section>
      )}

      {/* Decision maker hints */}
      {(result.decision_maker_hints?.length ?? 0) > 0 && (
        <Section title="Ключевые контакты (подсказки AI)">
          <div className="space-y-3">
            {result.decision_maker_hints.map((dm, i) => (
              <DecisionMakerCard key={i} hint={dm} />
            ))}
          </div>
        </Section>
      )}

      {/* Next steps */}
      {(result.next_steps?.length ?? 0) > 0 && (
        <Section title="Следующие шаги">
          <ol className="space-y-2">
            {result.next_steps.map((step, i) => (
              <li key={i} className="flex gap-3 text-sm text-ink/85">
                <span className="font-mono text-xs text-muted-3 mt-0.5 shrink-0 w-4">
                  {i + 1}.
                </span>
                {step}
              </li>
            ))}
          </ol>
        </Section>
      )}

      {/* Sources */}
      {(result.sources_used?.length ?? 0) > 0 && (
        <Section title="Источники">
          <div className="flex flex-wrap gap-1.5">
            {result.sources_used.map((src, i) => (
              <span
                key={i}
                className="text-xs font-mono px-2 py-0.5 rounded-md bg-black/5 text-muted-2"
              >
                {src}
              </span>
            ))}
          </div>
        </Section>
      )}

      {/* Notes */}
      {result.notes && (
        <p className="text-xs text-muted-2 italic border-t border-black/5 pt-4">
          {result.notes}
        </p>
      )}
    </div>
  );
}

function DecisionMakerCard({ hint }: { hint: DecisionMakerHint }) {
  const confidenceColor =
    hint.confidence === "high"
      ? "text-success bg-success/10"
      : hint.confidence === "medium"
      ? "text-warning bg-warning/10"
      : "text-muted bg-black/5";

  const roleLabel: Record<string, string> = {
    economic_buyer: "Экон. покупатель",
    champion: "Чемпион",
    technical_buyer: "Тех. покупатель",
    operational_buyer: "Опер. покупатель",
  };

  return (
    <div className="bg-canvas border border-black/5 rounded-xl px-4 py-3 flex items-start gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-ink">{hint.name}</p>
          {hint.role && (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-accent/10 text-accent">
              {roleLabel[hint.role] ?? hint.role}
            </span>
          )}
          <span
            className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${confidenceColor}`}
          >
            {hint.confidence}
          </span>
        </div>
        {hint.title && (
          <p className="text-xs text-muted-2 mt-0.5">{hint.title}</p>
        )}
        {hint.source && (
          <p className="text-[10px] font-mono text-muted-3 mt-1 truncate">{hint.source}</p>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 mb-2">
        {title}
      </p>
      {children}
    </div>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-canvas rounded-xl px-3 py-2.5 border border-black/5">
      <p className="text-[10px] font-mono uppercase tracking-wider text-muted-3 mb-0.5">{label}</p>
      <p className="text-sm text-ink/85">{value}</p>
    </div>
  );
}
