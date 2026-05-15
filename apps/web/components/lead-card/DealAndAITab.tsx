"use client";
import { useState } from "react";
import {
  Building2,
  MapPin,
  LayoutGrid,
  Globe,
  CircleDollarSign,
  Tag,
  User,
  Sparkles,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useLatestEnrichment, useTriggerEnrichment } from "@/lib/hooks/use-enrichment";
import { useUsers } from "@/lib/hooks/use-users";
import { ApiError } from "@/lib/api-client";
import type { LeadOut } from "@/lib/types";
import { dealTypeLabel } from "@/lib/i18n";
import { C } from "@/lib/design-system";

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

  const usersQuery = useUsers();
  const assignedUser = usersQuery.data?.items.find((u) => u.id === lead.assigned_to);
  const assignedLabel = assignedUser?.email
    ? assignedUser.email
    : lead.assigned_to
      ? lead.assigned_to.slice(0, 8)
      : "Не назначен";

  // City "Москва (HQ)" + chain hint when network_scale is populated.
  const cityLabel = lead.city ?? "";
  const networkScale = asText(ai.network_scale ?? ai.scale_signals);
  const isChain = /сет|магазин|аптек|филиал|stores?|outlets/i.test(networkScale);

  const formats = asList(ai.formats);
  const formatsText = formats.length > 0 ? formats.join(" · ") : asText(ai.formats);

  return (
    <div className="space-y-4">
      {/* === Card 1: О компании === */}
      <section className="bg-white rounded-2xl border border-brand-border p-5">
        <h2 className={`type-card-title font-bold ${C.color.text} mb-4`}>
          О компании
        </h2>
        <ul className="space-y-3.5">
          <Row
            icon={<Building2 size={16} className={C.color.muted} />}
            primary={
              asText(ai.company_profile) ||
              asText(ai.company_overview) ||
              "Описание не задано"
            }
          />
          {(cityLabel || isChain) && (
            <Row
              icon={<MapPin size={16} className={C.color.muted} />}
              primary={
                cityLabel
                  ? isChain
                    ? `${cityLabel} (HQ)`
                    : cityLabel
                  : "Город не указан"
              }
              hint={isChain && networkScale ? `Сеть · ${networkScale}` : undefined}
            />
          )}
          {(formatsText || asText(ai.scale_signals)) && (
            <Row
              icon={<LayoutGrid size={16} className={C.color.muted} />}
              primary={formatsText || asText(ai.scale_signals)}
              hint="Форматы и масштаб"
            />
          )}
          {lead.website && (
            <Row
              icon={<Globe size={16} className={C.color.muted} />}
              primary={
                <a
                  href={lead.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`${C.color.accent} hover:underline truncate inline-block max-w-full`}
                >
                  {lead.website.replace(/^https?:\/\//, "")}
                </a>
              }
            />
          )}
        </ul>
      </section>

      {/* === Card 2: Параметры сделки === */}
      <section className="bg-white rounded-2xl border border-brand-border p-5">
        <h2 className={`type-card-title font-bold ${C.color.text} mb-4`}>
          Параметры сделки
        </h2>
        <ul className="space-y-3.5">
          <Row
            icon={<CircleDollarSign size={16} className={C.color.muted} />}
            primary="Сумма сделки не указана"
            hint="Поле появится после интеграции CRM-формы суммы"
          />
          <Row
            icon={<Tag size={16} className={C.color.muted} />}
            primary={
              lead.deal_type ? dealTypeLabel(lead.deal_type) : "Тип сделки не выбран"
            }
          />
          <Row
            icon={<User size={16} className={C.color.muted} />}
            primary={assignedLabel}
            hint={lead.assigned_to ? "Ответственный менеджер" : undefined}
          />
        </ul>
      </section>

      {/* === Card 3: AI Бриф === */}
      <AIBriefCard lead={lead} hasAiData={hasAiData} ai={ai} />
    </div>
  );
}

function Row({
  icon,
  primary,
  hint,
}: {
  icon: React.ReactNode;
  primary: React.ReactNode;
  hint?: string;
}) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className={`type-caption ${C.color.text} leading-relaxed`}>{primary}</div>
        {hint && (
          <div className={`type-caption ${C.color.muted} mt-0.5`}>{hint}</div>
        )}
      </div>
    </li>
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

  function handleRun(mode: "full" | "append") {
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
          <button
            type="button"
            onClick={() => handleRun("append")}
            disabled={isRunning}
            className={`inline-flex items-center gap-1.5 px-4 py-1.5 type-body font-semibold ${C.button.ghost} disabled:opacity-50 transition-opacity`}
          >
            {isRunning ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            Дополнить
          </button>
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
