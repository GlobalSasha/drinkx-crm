"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useUpdateLead } from "@/lib/hooks/use-lead";
import type { LeadOut, Priority, DealType, LeadUpdateExtended } from "@/lib/types";
import { tierFromScore } from "@/lib/types";
import { priorityConfig } from "@/lib/ui/priority";

const DEAL_TYPE_OPTIONS: { value: DealType; label: string }[] = [
  { value: "enterprise_direct",  label: "Прямой enterprise-клиент" },
  { value: "qsr",                label: "QSR / high-volume foodservice" },
  { value: "distributor_partner", label: "Дистрибьютор / партнёр" },
  { value: "raw_materials",      label: "Сырьевой / стратегический партнёр" },
  { value: "private_small",      label: "Частный / малый клиент" },
  { value: "service_repeat",     label: "Сервис / повторная продажа" },
];

const PRIORITY_OPTIONS: Priority[] = ["A", "B", "C", "D"];

interface Props {
  lead: LeadOut;
}

export function DealTab({ lead }: Props) {
  const updateLead = useUpdateLead(lead.id);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [dealType, setDealType] = useState<DealType | "">(lead.deal_type ?? "");
  const [priority, setPriority] = useState<Priority | "">(lead.priority ?? "");
  const [score, setScore] = useState(lead.score ?? 0);
  const [blocker, setBlocker] = useState(lead.blocker ?? "");
  const [nextStep, setNextStep] = useState(lead.next_step ?? "");
  const [nextActionAt, setNextActionAt] = useState(
    lead.next_action_at ? lead.next_action_at.slice(0, 16) : ""
  );

  // Sync if lead prop changes externally
  useEffect(() => {
    setDealType(lead.deal_type ?? "");
    setPriority(lead.priority ?? "");
    setScore(lead.score ?? 0);
    setBlocker(lead.blocker ?? "");
    setNextStep(lead.next_step ?? "");
    setNextActionAt(lead.next_action_at ? lead.next_action_at.slice(0, 16) : "");
  }, [lead.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const patch = useCallback(
    (patch: LeadUpdateExtended) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        updateLead.mutate(patch);
      }, 600);
    },
    [updateLead]
  );

  function onDealTypeChange(v: string) {
    setDealType(v as DealType);
    patch({ deal_type: v as DealType });
  }

  function onPriorityChange(v: Priority) {
    setPriority(v);
    patch({ priority: v });
  }

  function onScoreChange(v: number) {
    setScore(v);
    patch({ score: v });
  }

  function onBlockerChange(v: string) {
    setBlocker(v);
    patch({ blocker: v || null });
  }

  function onNextStepChange(v: string) {
    setNextStep(v);
    patch({ next_step: v || null });
  }

  function onNextActionAtChange(v: string) {
    setNextActionAt(v);
    patch({ next_action_at: v || null });
  }

  const tier = tierFromScore(score);

  return (
    <div className="space-y-6">
      {/* Deal type */}
      <div>
        <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1.5">
          Тип сделки
        </label>
        <select
          value={dealType}
          onChange={(e) => onDealTypeChange(e.target.value)}
          className="w-full px-3 py-2.5 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 focus:bg-white transition-all"
        >
          <option value="">— не выбрано —</option>
          {DEAL_TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {/* Priority */}
      <div>
        <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1.5">
          Приоритет
        </label>
        <div className="flex gap-2">
          {PRIORITY_OPTIONS.map((p) => (
            <button
              key={p}
              onClick={() => onPriorityChange(p)}
              className={`flex-1 py-2 text-sm font-bold rounded-xl border transition-all ${
                priority === p
                  ? priorityConfig[p].chipBordered
                  : "bg-canvas text-muted border-black/10 hover:bg-canvas-2"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Score slider */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3">
            Score
          </label>
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-bold text-ink">{score}</span>
            <span
              className={`text-xs font-bold px-2 py-0.5 rounded-pill ${priorityConfig[tier as Priority]?.solid ?? "bg-muted text-white"}`}
            >
              {tier}
            </span>
          </div>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          value={score}
          onChange={(e) => onScoreChange(Number(e.target.value))}
          className="w-full accent-accent"
        />
        <div className="flex justify-between text-[10px] font-mono text-muted-3 mt-0.5">
          <span>0</span>
          <span>100</span>
        </div>
      </div>

      {/* Blocker */}
      <div>
        <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1.5">
          Блокер
        </label>
        <textarea
          value={blocker}
          onChange={(e) => onBlockerChange(e.target.value)}
          placeholder="Опишите блокер..."
          rows={3}
          className="w-full px-3 py-2.5 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 focus:bg-white resize-none transition-all"
        />
      </div>

      {/* Next step + date */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1.5">
            Следующий шаг
          </label>
          <input
            type="text"
            value={nextStep}
            onChange={(e) => onNextStepChange(e.target.value)}
            placeholder="Отправить КП..."
            className="w-full px-3 py-2.5 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 focus:bg-white transition-all"
          />
        </div>
        <div>
          <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1.5">
            Срок
          </label>
          <input
            type="datetime-local"
            value={nextActionAt}
            onChange={(e) => onNextActionAtChange(e.target.value)}
            className="w-full px-3 py-2.5 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 focus:bg-white transition-all"
          />
        </div>
      </div>
    </div>
  );
}
