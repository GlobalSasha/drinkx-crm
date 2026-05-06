"use client";

import { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Compass,
  Loader2,
  RefreshCw,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { useLatestEnrichment, useTriggerEnrichment } from "@/lib/hooks/use-enrichment";
import { ApiError } from "@/lib/api-client";
import type { DecisionMakerHint, EnrichmentRun, ResearchOutput } from "@/lib/types";

interface Props {
  leadId: string;
}

const URGENCY_LABEL: Record<string, string> = {
  high: "Высокий приоритет",
  medium: "Средний приоритет",
  low: "Низкий приоритет",
};

const ROLE_LABEL: Record<string, string> = {
  economic_buyer: "Экон. покупатель",
  champion: "Чемпион",
  technical_buyer: "Технический покупатель",
  operational_buyer: "Операционный покупатель",
};

const CONFIDENCE_LABEL: Record<string, string> = {
  high: "уверенно",
  medium: "вероятно",
  low: "под вопросом",
};

// Some result fields can come as either a string or an array (LLMs are
// inconsistent). Normalize to a readable string list.
function asList(v: string | string[] | null | undefined): string[] {
  if (!v) return [];
  if (Array.isArray(v)) return v.filter((s) => s && s.trim().length > 0);
  return [v];
}

function asText(v: string | string[] | null | undefined): string {
  if (!v) return "";
  if (Array.isArray(v)) return v.filter(Boolean).join(", ");
  return v;
}

// Detect the failure mode where Pydantic dropped raw JSON into `notes`
function looksLikeRawJson(s: string | undefined): boolean {
  if (!s) return false;
  const t = s.trim();
  return t.startsWith("{") && t.endsWith("}") && t.includes(":");
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
          showToast("Не удалось запустить enrichment");
        }
      },
    });
  }

  const isRunning = run?.status === "running" || trigger.isPending;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 size={22} className="animate-spin text-muted-3" />
      </div>
    );
  }

  return (
    <div className="space-y-7">
      {/* Header — clean, confident */}
      <header className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h2 className="text-2xl font-extrabold tracking-tight text-ink">AI Brief</h2>
          {run && (
            <RunMetaLine run={run} />
          )}
        </div>

        <button
          onClick={handleTrigger}
          disabled={isRunning}
          className="shrink-0 inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold bg-accent text-white rounded-pill hover:bg-accent/90 disabled:opacity-60 disabled:cursor-not-allowed transition-all duration-700 ease-soft active:scale-[0.98]"
        >
          {isRunning ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              Идёт enrichment…
            </>
          ) : run ? (
            <>
              <RefreshCw size={15} />
              Обновить
            </>
          ) : (
            <>
              <Sparkles size={15} />
              Запустить enrichment
            </>
          )}
        </button>
      </header>

      {run?.status === "running" && <RunningState startedAt={run.started_at} />}

      {run?.status === "failed" && (
        <FailureBanner run={run} onRetry={handleTrigger} retrying={trigger.isPending} />
      )}

      {run?.status === "succeeded" && run.result_json && (
        <ResultBody result={run.result_json} />
      )}

      {!run && run !== undefined && (
        <EmptyState onTrigger={handleTrigger} isPending={trigger.isPending} />
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-ink text-white text-sm font-semibold px-5 py-2.5 rounded-pill shadow-soft z-50">
          {toast}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RunMetaLine({ run }: { run: EnrichmentRun }) {
  const parts: string[] = [];
  if (run.provider) parts.push(run.provider);
  if (run.model) parts.push(run.model);
  if (run.duration_ms > 0) parts.push(`${(run.duration_ms / 1000).toFixed(1)} с`);
  if (Number(run.cost_usd) > 0) parts.push(`$${Number(run.cost_usd).toFixed(4)}`);
  parts.push(
    new Date(run.started_at).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }),
  );
  return (
    <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-3 mt-1.5">
      {parts.join(" · ")}
    </p>
  );
}

function RunningState({ startedAt }: { startedAt: string }) {
  const elapsed = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
  return (
    <div className="bg-white border border-black/5 rounded-2xl shadow-soft p-7">
      <div className="flex items-center gap-3 mb-5">
        <Loader2 size={18} className="text-accent animate-spin" />
        <div>
          <p className="text-base font-semibold text-ink">AI собирает данные</p>
          <p className="text-xs text-muted-2 mt-0.5">
            Brave · HH.ru · сайт компании · {elapsed} с
          </p>
        </div>
      </div>
      <div className="space-y-3">
        {[100, 70, 92, 55, 82].map((w, i) => (
          <div
            key={i}
            className="h-3.5 bg-black/[0.04] rounded-lg animate-pulse"
            style={{ width: `${w}%`, animationDelay: `${i * 120}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

function FailureBanner({
  run,
  onRetry,
  retrying,
}: {
  run: EnrichmentRun;
  onRetry: () => void;
  retrying: boolean;
}) {
  return (
    <div className="bg-rose/[0.04] border border-rose/20 rounded-2xl px-6 py-5">
      <div className="flex items-start gap-3 mb-4">
        <div className="w-9 h-9 rounded-xl bg-rose/10 flex items-center justify-center shrink-0">
          <AlertTriangle size={17} className="text-rose" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-base font-semibold text-rose">Enrichment не удался</p>
          {run.error && (
            <p className="text-sm text-rose/85 mt-1 line-clamp-3 break-words">{run.error}</p>
          )}
        </div>
      </div>
      <button
        onClick={onRetry}
        disabled={retrying}
        className="text-sm font-semibold text-rose hover:underline disabled:opacity-50"
      >
        Попробовать снова
      </button>
    </div>
  );
}

function EmptyState({ onTrigger, isPending }: { onTrigger: () => void; isPending: boolean }) {
  return (
    <div className="bg-white border border-black/5 rounded-2xl shadow-soft px-8 py-14">
      <div className="flex flex-col items-center text-center gap-5 max-w-sm mx-auto">
        <div className="w-14 h-14 rounded-2xl bg-accent/10 flex items-center justify-center">
          <Sparkles size={26} className="text-accent" />
        </div>
        <div>
          <h3 className="text-lg font-bold text-ink mb-1.5">Нет AI-обзора</h3>
          <p className="text-sm text-muted-2 leading-relaxed">
            AI соберёт данные из Brave, HH.ru и сайта компании, оценит совпадение
            с ICP и подготовит план следующих шагов.
          </p>
        </div>
        <button
          onClick={onTrigger}
          disabled={isPending}
          className="inline-flex items-center gap-2 px-6 py-3 text-sm font-semibold bg-accent text-white rounded-pill hover:bg-accent/90 disabled:opacity-60 transition-all duration-700 ease-soft active:scale-[0.98]"
        >
          {isPending ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Sparkles size={15} />
          )}
          Запустить enrichment
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Result body — the meat
// ---------------------------------------------------------------------------

function ResultBody({ result }: { result: ResearchOutput }) {
  const fitScore = Number(result.fit_score) || 0;
  const fitTier = fitScore >= 8 ? "hot" : fitScore >= 5 ? "warm" : "cold";
  const fitTone = {
    hot: "bg-warning/15 text-warning ring-warning/30",
    warm: "bg-accent/10 text-accent ring-accent/25",
    cold: "bg-black/5 text-muted-2 ring-black/10",
  }[fitTier];

  const formatsText = asText(result.formats);
  const coffeeSignals = asList(result.coffee_signals);
  const growthSignals = asList(result.growth_signals);
  const riskSignals = asList(result.risk_signals);

  const showHero = Boolean(
    result.company_profile || fitScore > 0 || result.urgency || result.network_scale,
  );

  const noteIsRawJson = looksLikeRawJson(result.notes);

  return (
    <div className="space-y-5">
      {/* HERO — profile + fit_score */}
      {showHero && (
        <section className="bg-white border border-black/5 rounded-2xl shadow-soft p-7">
          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-7 items-start">
            <div>
              {result.company_profile ? (
                <p className="text-base text-ink leading-[1.7]">
                  {result.company_profile}
                </p>
              ) : (
                <p className="text-sm text-muted-3 italic">
                  Профиль компании пока не сформирован.
                </p>
              )}
              {result.urgency && URGENCY_LABEL[result.urgency] && (
                <div className="mt-5">
                  <UrgencyChip urgency={result.urgency} />
                </div>
              )}
            </div>

            <FitScoreBadge fitScore={fitScore} tone={fitTone} />
          </div>
        </section>
      )}

      {/* QUICK FACTS strip */}
      {(result.network_scale || result.geography || formatsText) && (
        <section className="bg-white border border-black/5 rounded-2xl shadow-soft overflow-hidden">
          <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-black/5">
            {result.network_scale && (
              <FactCell icon={<Target size={14} />} label="Масштаб" value={result.network_scale} />
            )}
            {result.geography && (
              <FactCell icon={<Compass size={14} />} label="География" value={result.geography} />
            )}
            {formatsText && (
              <FactCell icon={<Target size={14} />} label="Форматы" value={formatsText} />
            )}
          </div>
        </section>
      )}

      {/* COFFEE SIGNALS — the thesis */}
      {coffeeSignals.length > 0 && (
        <section className="bg-accent/[0.04] border border-accent/15 rounded-2xl px-7 py-6">
          <div className="flex items-center gap-2 mb-3.5">
            <div className="w-7 h-7 rounded-lg bg-accent/15 flex items-center justify-center">
              <Sparkles size={13} className="text-accent" />
            </div>
            <h3 className="text-xs font-mono uppercase tracking-[0.16em] text-accent">
              Кофейные сигналы
            </h3>
          </div>
          <ul className="space-y-2 text-[15px] text-ink/90 leading-relaxed">
            {coffeeSignals.map((s, i) => (
              <li key={i} className="flex gap-3">
                <span className="text-accent mt-1.5 shrink-0 leading-none">●</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* GROWTH vs RISK — balance sheet */}
      {(growthSignals.length > 0 || riskSignals.length > 0) && (
        <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {growthSignals.length > 0 && (
            <SignalColumn
              label="Точки роста"
              icon={<TrendingUp size={13} />}
              items={growthSignals}
              tone="success"
            />
          )}
          {riskSignals.length > 0 && (
            <SignalColumn
              label="Риски"
              icon={<AlertCircle size={13} />}
              items={riskSignals}
              tone="rose"
            />
          )}
        </section>
      )}

      {/* DECISION MAKERS */}
      {(result.decision_maker_hints?.length ?? 0) > 0 && (
        <Section title="Ключевые контакты — подсказки">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {result.decision_maker_hints.map((dm, i) => (
              <DecisionMakerCard key={i} hint={dm} />
            ))}
          </div>
        </Section>
      )}

      {/* NEXT STEPS */}
      {(result.next_steps?.length ?? 0) > 0 && (
        <Section title="Следующие шаги">
          <ol className="space-y-2.5">
            {result.next_steps.map((step, i) => (
              <li
                key={i}
                className="bg-white border border-black/5 rounded-xl px-5 py-3.5 flex gap-3.5 items-start"
              >
                <span className="shrink-0 w-7 h-7 rounded-full bg-ink text-white font-mono text-xs font-semibold flex items-center justify-center">
                  {i + 1}
                </span>
                <p className="text-[15px] text-ink/90 leading-relaxed pt-0.5">{step}</p>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {/* FOOTER — sources + notes */}
      {((result.sources_used?.length ?? 0) > 0 || (result.notes && !noteIsRawJson)) && (
        <footer className="border-t border-black/5 pt-6 space-y-4">
          {(result.sources_used?.length ?? 0) > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-3 mb-2">
                Источники
              </p>
              <div className="flex flex-wrap gap-1.5">
                {result.sources_used.map((src, i) => (
                  <span
                    key={i}
                    className="text-[11px] font-mono px-2.5 py-1 rounded-md bg-black/[0.04] text-muted-2 border border-black/5"
                  >
                    {src}
                  </span>
                ))}
              </div>
            </div>
          )}
          {result.notes && !noteIsRawJson && (
            <p className="text-sm text-muted-2 italic leading-relaxed">{result.notes}</p>
          )}
        </footer>
      )}

      {/* Edge case: notes contains raw JSON (parser fallback) */}
      {noteIsRawJson && (
        <details className="bg-black/[0.03] border border-black/5 rounded-xl px-5 py-3 text-xs">
          <summary className="cursor-pointer text-muted-2 font-semibold">
            AI вернул нестандартный формат — показать сырой ответ
          </summary>
          <pre className="mt-3 font-mono text-[11px] text-muted-2 whitespace-pre-wrap break-words leading-relaxed">
            {result.notes}
          </pre>
        </details>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Atomic UI parts
// ---------------------------------------------------------------------------

function FitScoreBadge({ fitScore, tone }: { fitScore: number; tone: string }) {
  return (
    <div className="flex flex-col items-center gap-2.5 shrink-0">
      <div
        className={`w-24 h-24 rounded-3xl flex items-center justify-center ring-1 ${tone}`}
      >
        <span className="text-5xl font-extrabold tracking-tight tabular-nums leading-none">
          {fitScore.toFixed(fitScore % 1 === 0 ? 0 : 1)}
        </span>
      </div>
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-3">
        Fit&nbsp;score / 10
      </p>
    </div>
  );
}

function UrgencyChip({ urgency }: { urgency: string }) {
  const tone =
    urgency === "high"
      ? "bg-rose/10 text-rose border-rose/25"
      : urgency === "medium"
        ? "bg-warning/10 text-warning border-warning/25"
        : "bg-black/[0.04] text-muted-2 border-black/10";
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-pill border ${tone}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          urgency === "high"
            ? "bg-rose"
            : urgency === "medium"
              ? "bg-warning"
              : "bg-muted-3"
        }`}
      />
      {URGENCY_LABEL[urgency] ?? urgency}
    </span>
  );
}

function FactCell({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="px-6 py-5">
      <div className="flex items-center gap-1.5 mb-2 text-muted-3">
        {icon}
        <p className="font-mono text-[10px] uppercase tracking-[0.16em]">{label}</p>
      </div>
      <p className="text-[15px] text-ink/90 leading-snug">{value}</p>
    </div>
  );
}

function SignalColumn({
  label,
  icon,
  items,
  tone,
}: {
  label: string;
  icon: React.ReactNode;
  items: string[];
  tone: "success" | "rose";
}) {
  const headerTone = tone === "success" ? "text-success" : "text-rose";
  const dotTone = tone === "success" ? "bg-success/80" : "bg-rose/80";
  const bg = tone === "success" ? "bg-success/[0.04] border-success/15" : "bg-rose/[0.04] border-rose/15";
  return (
    <div className={`rounded-2xl border ${bg} px-6 py-5`}>
      <div className={`flex items-center gap-1.5 mb-3 ${headerTone}`}>
        {icon}
        <p className="font-mono text-[10px] uppercase tracking-[0.16em]">{label}</p>
      </div>
      <ul className="space-y-2">
        {items.map((s, i) => (
          <li key={i} className="flex gap-2.5 text-[14px] text-ink/85 leading-relaxed">
            <span className={`mt-2 shrink-0 w-1.5 h-1.5 rounded-full ${dotTone}`} />
            <span>{s}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DecisionMakerCard({ hint }: { hint: DecisionMakerHint }) {
  const initial = (hint.name || hint.title || "?").trim().charAt(0).toUpperCase();
  const confidenceTone =
    hint.confidence === "high"
      ? "bg-success/10 text-success"
      : hint.confidence === "medium"
        ? "bg-warning/10 text-warning"
        : "bg-black/[0.04] text-muted-2";
  const roleLabel = ROLE_LABEL[hint.role] ?? (hint.role || null);

  return (
    <div className="bg-white border border-black/5 rounded-2xl p-4 flex gap-3.5 shadow-soft">
      <div className="shrink-0 w-11 h-11 rounded-xl bg-accent/10 text-accent flex items-center justify-center text-base font-extrabold">
        {initial}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[15px] font-bold text-ink truncate">
          {hint.name || <span className="text-muted-3 italic font-medium">имя не указано</span>}
        </p>
        {hint.title && (
          <p className="text-xs text-muted-2 mt-0.5 truncate">{hint.title}</p>
        )}
        <div className="flex flex-wrap items-center gap-1.5 mt-2">
          {roleLabel && (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-accent/10 text-accent uppercase tracking-wider">
              {roleLabel}
            </span>
          )}
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${confidenceTone}`}>
            {CONFIDENCE_LABEL[hint.confidence] ?? hint.confidence}
          </span>
        </div>
        {hint.source && (
          <p className="text-[10px] font-mono text-muted-3 mt-2 truncate">{hint.source}</p>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-3 mb-3">
        {title}
      </h3>
      {children}
    </section>
  );
}
