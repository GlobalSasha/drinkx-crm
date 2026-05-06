"use client";
import { useState, useEffect } from "react";
import { useUpdateLead } from "@/lib/hooks/use-lead";
import type { LeadOut } from "@/lib/types";

// Pilot contract fields per ADR-011
interface PilotContract {
  goal: string;
  period_start: string;
  period_end: string;
  locations: string;
  // Success metrics
  cups_per_day: string;
  uptime: string;
  avg_check: string;
  service_time: string;
  incidents_per_month: string;
  baseline: string;
  // Responsible
  responsible_client: string;
  responsible_drinkx: string;
  review_date: string;
  decision: string;
}

const EMPTY_CONTRACT: PilotContract = {
  goal: "",
  period_start: "",
  period_end: "",
  locations: "",
  cups_per_day: "",
  uptime: "",
  avg_check: "",
  service_time: "",
  incidents_per_month: "",
  baseline: "",
  responsible_client: "",
  responsible_drinkx: "",
  review_date: "",
  decision: "",
};

interface Props {
  lead: LeadOut;
}

export function PilotTab({ lead }: Props) {
  const updateLead = useUpdateLead(lead.id);

  const [contract, setContract] = useState<PilotContract>(() => {
    const saved = lead.pilot_contract_json ?? {};
    return { ...EMPTY_CONTRACT, ...saved };
  });

  // Sync when lead id changes
  useEffect(() => {
    const saved = lead.pilot_contract_json ?? {};
    setContract({ ...EMPTY_CONTRACT, ...saved });
  }, [lead.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSave() {
    updateLead.mutate({ pilot_contract_json: contract });
  }

  function field(key: keyof PilotContract) {
    return {
      value: contract[key],
      onChange: (
        e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
      ) => setContract((prev) => ({ ...prev, [key]: e.target.value })),
    };
  }

  return (
    <div className="space-y-6">
      <div className="bg-accent/5 border border-accent/15 rounded-xl px-4 py-3">
        <p className="text-sm font-semibold text-accent">Pilot Success Contract (ADR-011)</p>
        <p className="text-xs text-muted-2 mt-0.5">
          Заполните условия пилота перед запуском
        </p>
      </div>

      {/* Goal */}
      <FormSection title="Цель пилота">
        <textarea
          {...field("goal")}
          rows={3}
          placeholder="Цель и ожидаемый результат..."
          className="w-full px-3 py-2.5 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-accent/40 resize-none transition-all"
        />
      </FormSection>

      {/* Period */}
      <FormSection title="Период">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-3 block mb-1">
              Начало
            </label>
            <input
              type="date"
              {...field("period_start")}
              className="w-full px-3 py-2 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
            />
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-3 block mb-1">
              Конец
            </label>
            <input
              type="date"
              {...field("period_end")}
              className="w-full px-3 py-2 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
            />
          </div>
        </div>
      </FormSection>

      {/* Locations */}
      <FormSection title="Локации">
        <input
          type="text"
          {...field("locations")}
          placeholder="Список локаций через запятую..."
          className="w-full px-3 py-2.5 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
        />
      </FormSection>

      {/* Success metrics */}
      <FormSection title="Метрики успеха">
        <div className="grid grid-cols-2 gap-3">
          {(
            [
              ["cups_per_day", "Кружек/день"],
              ["uptime", "Uptime %"],
              ["avg_check", "Средний чек"],
              ["service_time", "Время сервиса"],
              ["incidents_per_month", "Инцидентов/мес"],
              ["baseline", "Базовый уровень"],
            ] as [keyof PilotContract, string][]
          ).map(([key, label]) => (
            <div key={key}>
              <label className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-3 block mb-1">
                {label}
              </label>
              <input
                type="text"
                {...field(key)}
                className="w-full px-3 py-2 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
              />
            </div>
          ))}
        </div>
      </FormSection>

      {/* Responsible */}
      <FormSection title="Ответственные">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-3 block mb-1">
              Со стороны клиента
            </label>
            <input
              type="text"
              {...field("responsible_client")}
              className="w-full px-3 py-2 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
            />
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-3 block mb-1">
              Со стороны DrinkX
            </label>
            <input
              type="text"
              {...field("responsible_drinkx")}
              className="w-full px-3 py-2 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
            />
          </div>
        </div>
      </FormSection>

      {/* Review + decision */}
      <FormSection title="Результат">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-3 block mb-1">
              Дата ревью
            </label>
            <input
              type="date"
              {...field("review_date")}
              className="w-full px-3 py-2 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
            />
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-3 block mb-1">
              Решение
            </label>
            <select
              {...field("decision")}
              className="w-full px-3 py-2 text-sm bg-canvas border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
            >
              <option value="">— не выбрано —</option>
              <option value="scale">Scale</option>
              <option value="extend">Extend</option>
              <option value="reject">Reject</option>
              <option value="refine">Refine</option>
            </select>
          </div>
        </div>
      </FormSection>

      {/* Save */}
      <button
        onClick={handleSave}
        disabled={updateLead.isPending}
        className="w-full py-2.5 rounded-pill text-sm font-semibold bg-ink text-white hover:bg-ink/90 disabled:opacity-50 transition-all"
      >
        {updateLead.isPending ? "Сохранение..." : "Сохранить Pilot Contract"}
      </button>
    </div>
  );
}

function FormSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 mb-2">
        {title}
      </p>
      {children}
    </div>
  );
}
