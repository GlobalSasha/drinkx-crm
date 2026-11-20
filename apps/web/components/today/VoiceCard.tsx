"use client";
// «Голос клиентов» on the head/admin /today: what clients say, from manager
// comments. An AI worker sorts each comment into a fixed list of categories and
// must quote it; the CRM keeps only tags whose quote is really in the comment.
// So every number here opens into the words it came from.
// Data: GET /company/voice?period=week|month.
import { useState, type ReactNode } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Info,
  MessageSquareWarning,
  PhoneOff,
  Swords,
  ThumbsUp,
  XCircle,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { C } from "@/lib/design-system";
import { useCompanyVoice } from "@/lib/hooks/use-company";
import type { VoiceGroup, VoiceItem } from "@/lib/types";

type Period = "week" | "month";

const PERIODS: { key: Period; label: string }[] = [
  { key: "week", label: "Неделя" },
  { key: "month", label: "Месяц" },
];

const GROUP_ICON: Record<VoiceGroup["group"], ReactNode> = {
  objection: <MessageSquareWarning size={16} aria-hidden />,
  question: <CircleHelp size={16} aria-hidden />,
  interest: <ThumbsUp size={16} aria-hidden />,
  competitor: <Swords size={16} aria-hidden />,
  contact: <PhoneOff size={16} aria-hidden />,
};

// Objections and contact trouble are the «bad» side — their bars are rose;
// interest is good news; questions and competitors are neutral information.
const GROUP_BAR: Record<VoiceGroup["group"], string> = {
  objection: "bg-rose/70",
  question: "bg-info/70",
  interest: "bg-success/70",
  competitor: "bg-warning/70",
  contact: "bg-brand-muted/50",
};

export function leadsWord(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "лид";
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "лида";
  return "лидов";
}

export function VoiceCard() {
  const [period, setPeriod] = useState<Period>("week");
  const [rulesOpen, setRulesOpen] = useState(false);
  const { data, isLoading, isError } = useCompanyVoice(period);

  const max = Math.max(1, ...(data?.groups.flatMap((g) => g.items.map((i) => i.leads)) ?? [1]));

  return (
    <Card className="mb-5">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="type-card-title text-brand-primary">Голос клиентов</h3>
            <button
              type="button"
              onClick={() => setRulesOpen((v) => !v)}
              aria-expanded={rulesOpen}
              aria-label="Откуда эти данные"
              className={`w-7 h-7 inline-flex items-center justify-center rounded-full text-brand-muted hover:bg-brand-panel transition-colors ${C.focusRing}`}
            >
              <Info size={16} aria-hidden />
            </button>
          </div>
          <p className="type-hint not-italic text-brand-muted">Что клиенты говорят менеджерам</p>
        </div>
        <div
          className="inline-flex self-start bg-brand-panel rounded-full p-1 gap-0.5"
          role="tablist"
          aria-label="Период"
        >
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              role="tab"
              aria-selected={period === p.key}
              onClick={() => setPeriod(p.key)}
              className={`px-4 py-1.5 rounded-full type-button transition-colors ${C.focusRing} ${
                period === p.key
                  ? "bg-white text-brand-primary shadow-sm"
                  : "text-brand-muted hover:text-brand-primary"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {rulesOpen && (
        <div className="mb-4 rounded-lg bg-brand-bg p-4 type-body text-brand-muted-strong space-y-1">
          <p>Каждую ночь ИИ читает новые комментарии менеджеров и относит их к темам из списка.</p>
          <p>К каждой отметке он обязан приложить цитату; если цитаты в комментарии нет, отметка отбрасывается.</p>
          <p>Число — сколько разных лидов, а не комментариев. Причины отказов берутся из окна «Сделка проиграна», без ИИ.</p>
        </div>
      )}

      {isError ? (
        <p className="type-body text-rose py-6 text-center">Не удалось загрузить — обновите страницу.</p>
      ) : isLoading || !data ? (
        <div className="h-24 rounded-lg bg-brand-panel animate-pulse" aria-hidden />
      ) : data.groups.length === 0 && data.lost_reasons.length === 0 ? (
        <p className="type-body text-brand-muted py-6 text-center">
          {data.comments_pending > 0
            ? `Комментарии ещё не разобраны: ${data.comments_pending} ждут ночной разметки.`
            : "За этот период в комментариях ничего не отмечено."}
        </p>
      ) : (
        <div className="space-y-6">
          {data.groups.map((g) => (
            <GroupBlock key={g.group} group={g} max={max} />
          ))}
          {data.lost_reasons.length > 0 && (
            <section aria-label="Причины отказов">
              <h4 className="inline-flex items-center gap-2 type-caption text-brand-muted mb-2">
                <XCircle size={16} aria-hidden />
                Причины отказов
              </h4>
              <ul className="flex flex-wrap gap-2">
                {data.lost_reasons.map((r) => (
                  <li
                    key={r.reason}
                    className="inline-flex items-center gap-2 h-7 px-3 rounded-full bg-rose/10 text-rose type-label"
                  >
                    {r.reason}
                    <span className="tabular-nums">{r.count}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

    </Card>
  );
}

function GroupBlock({ group, max }: { group: VoiceGroup; max: number }) {
  return (
    <section aria-label={group.label}>
      <h4 className="inline-flex items-center gap-2 type-caption text-brand-muted mb-2">
        {GROUP_ICON[group.group]}
        {group.label}
      </h4>
      <ul>
        {group.items.map((it) => (
          <VoiceRow key={it.key} item={it} max={max} bar={GROUP_BAR[group.group]} />
        ))}
      </ul>
    </section>
  );
}

function VoiceRow({ item, max, bar }: { item: VoiceItem; max: number; bar: string }) {
  const [open, setOpen] = useState(false);
  const delta = item.leads - item.previous;
  return (
    <li className="border-t border-brand-border first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={`w-full grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,240px)_minmax(0,1fr)_auto] items-center gap-3 py-2 text-left rounded-md hover:bg-brand-bg transition-colors ${C.focusRing}`}
      >
        <span className="inline-flex items-center gap-2 min-w-0">
          {open ? (
            <ChevronDown size={14} className="shrink-0 text-brand-muted" aria-hidden />
          ) : (
            <ChevronRight size={14} className="shrink-0 text-brand-muted" aria-hidden />
          )}
          <span className="truncate type-body text-brand-primary">{item.label}</span>
        </span>
        <span className="hidden sm:flex h-2 rounded-full bg-brand-panel overflow-hidden" aria-hidden>
          <span className={bar} style={{ width: `${(item.leads / max) * 100}%` }} />
        </span>
        <span className="inline-flex items-center gap-2 justify-end">
          <span className="type-label text-brand-primary tabular-nums whitespace-nowrap">
            {item.leads} {leadsWord(item.leads)}
          </span>
          {delta !== 0 && (
            <span
              className="inline-flex items-center type-hint not-italic text-brand-muted tabular-nums"
              title={`в прошлом периоде: ${item.previous}`}
            >
              {delta > 0 ? <ArrowUp size={12} aria-hidden /> : <ArrowDown size={12} aria-hidden />}
              {Math.abs(delta)}
            </span>
          )}
        </span>
      </button>
      {open && (
        <ul className="mb-2 ml-6 rounded-lg bg-brand-bg px-4 py-1">
          {item.quotes.map((q) => (
            <li key={`${q.lead_id}-${q.at}`} className="border-t border-brand-border first:border-t-0 py-2">
              <p className="type-body text-brand-primary">«{q.quote}»</p>
              <Link
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                href={`/leads/${q.lead_id}` as any}
                className={`inline-flex items-center gap-1 type-hint not-italic text-brand-muted hover:text-brand-accent-text transition-colors rounded-md ${C.focusRing}`}
              >
                {q.company_name}
                {q.author ? ` · ${q.author}` : ""}
                <ChevronRight size={12} aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
